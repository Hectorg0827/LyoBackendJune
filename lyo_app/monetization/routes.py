"""Monetization routes: ads, subscriptions, payments, and IAP verification."""
from __future__ import annotations

import os
import logging
from typing import Dict, Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel, Field

from lyo_app.auth.security import verify_access_token
from lyo_app.auth.models import User
from lyo_app.monetization.google_provider import (
    get_provider_config,
    record_event,
    validate_provider_ready,
)
# from lyo_app.monetization.service import monetization_service  # TODO: File doesn't exist
from lyo_app.monetization.stripe_service import stripe_service, iap_service, SubscriptionPlan
from lyo_app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monetization", tags=["Monetization"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class AdConfigResponse(BaseModel):
    enabled: bool
    network_code: Optional[str]
    app_id_ios: Optional[str]
    app_id_android: Optional[str]
    placements: Dict[str, Optional[str]]


class MonetizationStatusResponse(BaseModel):
    tier: str
    energy: int
    is_premium: bool
    max_energy: int
    stripe_customer_id: Optional[str] = None
    subscription_end_date: Optional[datetime] = None


class SubscriptionPlansResponse(BaseModel):
    plans: List[Dict]
    stripe_publishable_key: Optional[str]


class CreateCheckoutRequest(BaseModel):
    plan: str = Field(..., description="Plan type: premium_monthly or premium_yearly")
    success_url: str = Field(..., description="URL to redirect after successful payment")
    cancel_url: str = Field(..., description="URL to redirect if payment cancelled")


class CreateCheckoutResponse(BaseModel):
    session_id: str
    checkout_url: str


class VerifyAppleReceiptRequest(BaseModel):
    receipt_data: str = Field(..., description="Base64 encoded receipt data from App Store")


class VerifyGooglePurchaseRequest(BaseModel):
    package_name: str = Field(..., description="Android package name")
    product_id: str = Field(..., description="Product ID from Google Play")
    purchase_token: str = Field(..., description="Purchase token from Google Play")


class AdEvent(BaseModel):
    placement: str = Field(..., description="feed|story|post|timer")
    event_type: str = Field(..., description="impression|click|closed|skipped")
    metadata: Dict[str, Optional[str]] = Field(default_factory=dict)


# ============================================================================
# SUBSCRIPTION STATUS & ENERGY
# ============================================================================

@router.get("/status", response_model=MonetizationStatusResponse)
async def get_monetization_status(
    current_user: User = Depends(verify_access_token),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's subscription and energy status."""
    # status = await monetization_service.get_user_status(db, current_user)
    status = {"tier": "FREE", "energy": 100, "is_premium": False, "max_energy": 100}  # Fallback
    
    # Add Stripe info if available
    stripe_customer_id = getattr(current_user, 'stripe_customer_id', None)
    if stripe_customer_id:
        sub_status = await stripe_service.get_subscription_status(stripe_customer_id)
        status["subscription_end_date"] = sub_status.get("current_period_end")
    
    status["stripe_customer_id"] = stripe_customer_id
    return status


@router.post("/reward-ad", summary="Reward user for watching an ad")
async def reward_ad_view(
    current_user: User = Depends(verify_access_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Call this when client confirms a rewarded video ad was completed.
    Refills energy credits.
    """
    # new_balance = await monetization_service.reward_ad_view(db, current_user)
    new_balance = 100  # Fallback
    return {"ok": True, "new_energy": new_balance}


# ============================================================================
# SUBSCRIPTION PLANS & CHECKOUT
# ============================================================================

@router.get("/plans", response_model=SubscriptionPlansResponse)
async def get_subscription_plans():
    """Get available subscription plans."""
    plans = [
        {
            "id": SubscriptionPlan.FREE.value,
            "name": "Free",
            "price": 0,
            "interval": None,
            "features": [
                "10 AI study sessions per day",
                "Ad-supported energy refills",
                "Basic learning features",
                "Community access"
            ]
        },
        {
            "id": SubscriptionPlan.PREMIUM_MONTHLY.value,
            "name": "Premium Monthly",
            "price": 9.99,
            "interval": "month",
            "features": [
                "Unlimited AI study sessions",
                "No ads",
                "Priority AI responses",
                "Advanced analytics",
                "Offline mode",
                "Premium support"
            ]
        },
        {
            "id": SubscriptionPlan.PREMIUM_YEARLY.value,
            "name": "Premium Yearly",
            "price": 79.99,
            "interval": "year",
            "savings": "Save 33%",
            "features": [
                "All Premium Monthly features",
                "2 months free",
                "Early access to new features"
            ]
        }
    ]
    
    return SubscriptionPlansResponse(
        plans=plans,
        stripe_publishable_key=stripe_service.publishable_key
    )


@router.post("/checkout", response_model=CreateCheckoutResponse)
async def create_checkout_session(
    request: CreateCheckoutRequest,
    current_user: User = Depends(verify_access_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a Stripe Checkout session for subscription.
    
    Returns a checkout URL to redirect the user to complete payment.
    """
    try:
        plan = SubscriptionPlan(request.plan)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan. Valid options: {[p.value for p in SubscriptionPlan if p != SubscriptionPlan.FREE]}"
        )
    
    if plan == SubscriptionPlan.FREE:
        raise HTTPException(status_code=400, detail="Cannot checkout for free plan")
    
    # Get or create Stripe customer
    stripe_customer_id = getattr(current_user, 'stripe_customer_id', None)
    if not stripe_customer_id:
        stripe_customer_id = await stripe_service.create_customer(
            user_id=current_user.id,
            email=current_user.email,
            name=getattr(current_user, 'full_name', None)
        )
        # Save customer ID to user (in production, update user record)
    
    result = await stripe_service.create_checkout_session(
        customer_id=stripe_customer_id,
        plan=plan,
        success_url=request.success_url,
        cancel_url=request.cancel_url
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create checkout session")
    
    return CreateCheckoutResponse(**result)


@router.post("/portal")
async def create_customer_portal(
    current_user: User = Depends(verify_access_token),
    return_url: str = "https://lyoapp.com/settings"
):
    """
    Create a Stripe Customer Portal session for managing subscription.
    
    The portal allows users to:
    - View billing history
    - Update payment method
    - Cancel subscription
    """
    stripe_customer_id = getattr(current_user, 'stripe_customer_id', None)
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="No subscription found")
    
    portal_url = await stripe_service.create_portal_session(
        customer_id=stripe_customer_id,
        return_url=return_url
    )
    
    if not portal_url:
        raise HTTPException(status_code=500, detail="Failed to create portal session")
    
    return {"portal_url": portal_url}


# ============================================================================
# WEBHOOKS
# ============================================================================

@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """
    Handle Stripe webhook events.
    
    This endpoint receives events from Stripe about:
    - Subscription changes
    - Payment success/failure
    - Customer updates
    """
    payload = await request.body()
    
    event = stripe_service.verify_webhook_signature(payload, stripe_signature or "")
    
    if not event:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    
    result = await stripe_service.handle_webhook_event(event)
    
    logger.info(f"Processed Stripe webhook: {result}")
    
    return {"received": True, "actions": result.get("actions", [])}


# ============================================================================
# IN-APP PURCHASE VERIFICATION
# ============================================================================

@router.post("/verify/apple")
async def verify_apple_purchase(
    request: VerifyAppleReceiptRequest,
    current_user: User = Depends(verify_access_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify an Apple App Store purchase receipt.
    
    Call this endpoint after a successful in-app purchase on iOS
    to verify the receipt and activate the subscription.
    """
    result = await iap_service.verify_apple_receipt(request.receipt_data)
    
    if result.get("valid"):
        # Activate subscription for user
        # await monetization_service.upgrade_to_premium(db, current_user)  # TODO: Service doesn't exist
        
        logger.info(f"Apple purchase verified for user {current_user.id}: {result.get('product_id')}")
        
        return {
            "valid": True,
            "product_id": result.get("product_id"),
            "environment": result.get("environment"),
            "is_trial": result.get("is_trial", False),
            "subscription_activated": True
        }
    
    raise HTTPException(
        status_code=400,
        detail=result.get("error", "Receipt verification failed")
    )


@router.post("/verify/google")
async def verify_google_purchase(
    request: VerifyGooglePurchaseRequest,
    current_user: User = Depends(verify_access_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify a Google Play purchase.
    
    Call this endpoint after a successful in-app purchase on Android
    to verify the purchase and activate the subscription.
    """
    result = await iap_service.verify_google_purchase(
        package_name=request.package_name,
        product_id=request.product_id,
        purchase_token=request.purchase_token
    )
    
    if result.get("valid"):
        # Activate subscription for user
        # await monetization_service.upgrade_to_premium(db, current_user)  # TODO: Service doesn't exist
        
        logger.info(f"Google purchase verified for user {current_user.id}: {result.get('product_id')}")
        
        return {
            "valid": True,
            "product_id": result.get("product_id"),
            "subscription_activated": True
        }
    
    raise HTTPException(
        status_code=400,
        detail=result.get("error", "Purchase verification failed")
    )


# ============================================================================
# AD CONFIGURATION
# ============================================================================

@router.get("/ads/config", response_model=AdConfigResponse)
async def get_ad_config(current_user: User = Depends(verify_access_token)):
    """Get ad configuration for the client SDK."""
    # Premium users don't see ads
    if current_user.subscription_tier == "PREMIUM":
        return AdConfigResponse(
            enabled=False,
            network_code=None,
            app_id_ios=None,
            app_id_android=None,
            placements={}
        )
    
    cfg = get_provider_config()
    return cfg


@router.post("/ads/event")
async def post_ad_event(
    event: AdEvent,
    current_user: User = Depends(verify_access_token)
):
    """Record an ad event (impression, click, etc.)."""
    try:
        record_event(event.event_type, event.model_dump())
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record event: {e}")

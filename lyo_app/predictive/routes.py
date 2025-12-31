"""
API routes for Predictive Intelligence System
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from lyo_app.core.database import get_db
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User

from .schemas import (
    StrugglePredictionRequest,
    StrugglePredictionResponse,
    DropoutRiskResponse,
    TimingProfileResponse,
    RecommendedTimeResponse,
    CheckTimingRequest,
    CheckTimingResponse,
    RecordOutcomeRequest,
    RecordOutcomeResponse,
    LearningPlateauResponse,
    SkillRegressionResponse,
    PredictiveInsightsResponse
)
from .struggle_predictor import struggle_predictor
from .dropout_prevention import dropout_predictor
from .optimal_timing import timing_optimizer
from .models import LearningPlateau, SkillRegression

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictive", tags=["Predictive Intelligence"])


@router.post("/struggle/predict", response_model=StrugglePredictionResponse)
async def predict_struggle(
    request: StrugglePredictionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Predict if user will struggle with content BEFORE they attempt it.
    Returns struggle probability and optional preemptive help message.
    """
    try:
        content_metadata = request.content_metadata.dict()

        # Get struggle prediction
        struggle_prob, confidence, features = await struggle_predictor.predict_struggle(
            current_user.id,
            content_metadata['content_id'],
            content_metadata,
            db
        )

        # Check if we should offer preemptive help
        should_offer, help_message = await struggle_predictor.should_offer_preemptive_help(
            current_user.id,
            content_metadata['content_id'],
            content_metadata,
            db
        )

        # Get the prediction ID (most recent prediction for this content)
        from .models import StrugglePrediction
        stmt = select(StrugglePrediction).where(
            and_(
                StrugglePrediction.user_id == current_user.id,
                StrugglePrediction.content_id == content_metadata['content_id']
            )
        ).order_by(StrugglePrediction.predicted_at.desc()).limit(1)

        result = await db.execute(stmt)
        prediction = result.scalar_one_or_none()

        return StrugglePredictionResponse(
            struggle_probability=struggle_prob,
            confidence=confidence,
            should_offer_help=should_offer,
            help_message=help_message,
            features=features,
            prediction_id=prediction.id if prediction else 0
        )

    except Exception as e:
        logger.error(f"Error predicting struggle for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to predict struggle"
        )


@router.post("/struggle/record-outcome", response_model=RecordOutcomeResponse)
async def record_struggle_outcome(
    request: RecordOutcomeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Record actual outcome after user attempts content.
    Used to improve prediction accuracy over time.
    """
    try:
        await struggle_predictor.record_actual_outcome(
            current_user.id,
            request.content_id,
            request.struggled,
            db
        )

        return RecordOutcomeResponse(
            success=True,
            message="Outcome recorded successfully"
        )

    except Exception as e:
        logger.error(f"Error recording outcome for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record outcome"
        )


@router.get("/dropout/risk", response_model=DropoutRiskResponse)
async def get_dropout_risk(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current dropout/churn risk assessment for user.
    Includes risk factors and recommended re-engagement strategy.
    """
    try:
        risk_score, risk_level, factors, metrics = await dropout_predictor.calculate_dropout_risk(
            current_user.id,
            db
        )

        # Get or generate re-engagement strategy
        strategy = None
        if risk_score > 0.5:
            strategy = await dropout_predictor.generate_reengagement_strategy(
                current_user.id,
                risk_score,
                factors,
                db
            )

        return DropoutRiskResponse(
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=factors,
            session_frequency_trend=metrics.get('session_frequency_trend'),
            avg_days_between_sessions=metrics.get('avg_days_between_sessions'),
            sentiment_trend_7d=metrics.get('sentiment_trend_7d'),
            days_since_last_completion=metrics.get('days_since_last_completion'),
            performance_trend=metrics.get('performance_trend'),
            longest_streak=metrics.get('longest_streak'),
            current_streak=metrics.get('current_streak'),
            reengagement_strategy=strategy,
            calculated_at=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Error calculating dropout risk for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate dropout risk"
        )


@router.get("/timing/profile", response_model=TimingProfileResponse)
async def get_timing_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get user's optimal learning time profile.
    Analyzes historical performance to identify peak hours and best days.
    """
    try:
        profile = await timing_optimizer.analyze_user_timing(
            current_user.id,
            db
        )

        return TimingProfileResponse(
            user_id=current_user.id,
            peak_hours=profile.get('peak_hours', []),
            optimal_study_time=profile.get('optimal_study_time'),
            best_days=profile.get('best_days', []),
            avg_session_duration_minutes=profile.get('avg_session_duration'),
            preferred_session_length=profile.get('preferred_session_length'),
            performance_by_hour={str(k): v for k, v in profile.get('performance_by_hour', {}).items()},
            most_active_hour=profile.get('most_active_hour'),
            least_active_hour=profile.get('least_active_hour'),
            typical_study_days=profile.get('typical_study_days', []),
            sessions_analyzed=profile.get('sessions_analyzed', 0),
            confidence=profile.get('confidence', 0.0),
            updated_at=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Error getting timing profile for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get timing profile"
        )


@router.get("/timing/recommended", response_model=RecommendedTimeResponse)
async def get_recommended_time(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get recommended time to send intervention for maximum engagement.
    """
    try:
        recommended_time = await timing_optimizer.get_recommended_intervention_time(
            current_user.id,
            db
        )

        return RecommendedTimeResponse(
            recommended_time=recommended_time,
            reasoning="Based on your historical peak performance times",
            confidence=0.8
        )

    except Exception as e:
        logger.error(f"Error getting recommended time for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get recommended time"
        )


@router.post("/timing/check", response_model=CheckTimingResponse)
async def check_timing(
    request: CheckTimingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if now (or specified time) is a good time to send intervention.
    """
    try:
        current_time = request.current_time or datetime.utcnow()

        is_good_time = await timing_optimizer.should_send_intervention_now(
            current_user.id,
            current_time,
            db
        )

        reasoning = "This aligns with your peak learning hours" if is_good_time else "Not your typical study time"

        alternative_time = None
        if not is_good_time:
            alternative_time = await timing_optimizer.get_recommended_intervention_time(
                current_user.id,
                db
            )

        return CheckTimingResponse(
            is_good_time=is_good_time,
            reasoning=reasoning,
            alternative_time=alternative_time
        )

    except Exception as e:
        logger.error(f"Error checking timing for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check timing"
        )


@router.get("/plateaus", response_model=list[LearningPlateauResponse])
async def get_learning_plateaus(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detected learning plateaus where user is stuck on topics.
    """
    try:
        stmt = select(LearningPlateau).where(
            LearningPlateau.user_id == current_user.id
        )

        if active_only:
            stmt = stmt.where(
                and_(
                    LearningPlateau.is_active == True,
                    LearningPlateau.resolved == False
                )
            )

        stmt = stmt.order_by(LearningPlateau.detected_at.desc())

        result = await db.execute(stmt)
        plateaus = result.scalars().all()

        return [
            LearningPlateauResponse(
                plateau_id=p.id,
                topic=p.topic,
                skill_id=p.skill_id,
                days_on_topic=p.days_on_topic,
                attempts=p.attempts,
                mastery_level=p.mastery_level,
                mastery_improvement=p.mastery_improvement,
                is_active=p.is_active,
                intervention_suggested=p.intervention_suggested,
                detected_at=p.detected_at
            )
            for p in plateaus
        ]

    except Exception as e:
        logger.error(f"Error getting plateaus for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get learning plateaus"
        )


@router.get("/regressions", response_model=list[SkillRegressionResponse])
async def get_skill_regressions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detected skill regressions where mastery is declining.
    """
    try:
        stmt = select(SkillRegression).where(
            SkillRegression.user_id == current_user.id
        ).order_by(SkillRegression.detected_at.desc())

        result = await db.execute(stmt)
        regressions = result.scalars().all()

        return [
            SkillRegressionResponse(
                regression_id=r.id,
                skill_id=r.skill_id,
                skill_name=r.skill_name,
                peak_mastery=r.peak_mastery,
                current_mastery=r.current_mastery,
                regression_amount=r.regression_amount,
                days_since_practice=r.days_since_practice,
                last_practiced_at=r.last_practiced_at,
                urgency=r.urgency,
                reminder_sent=r.reminder_sent,
                detected_at=r.detected_at
            )
            for r in regressions
        ]

    except Exception as e:
        logger.error(f"Error getting regressions for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get skill regressions"
        )


@router.get("/insights", response_model=PredictiveInsightsResponse)
async def get_predictive_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive predictive insights dashboard for user.
    Combines dropout risk, plateaus, regressions, and timing recommendations.
    """
    try:
        # Get dropout risk
        risk_score, risk_level, factors, metrics = await dropout_predictor.calculate_dropout_risk(
            current_user.id,
            db
        )

        dropout_risk = DropoutRiskResponse(
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=factors,
            session_frequency_trend=metrics.get('session_frequency_trend'),
            avg_days_between_sessions=metrics.get('avg_days_between_sessions'),
            sentiment_trend_7d=metrics.get('sentiment_trend_7d'),
            days_since_last_completion=metrics.get('days_since_last_completion'),
            performance_trend=metrics.get('performance_trend'),
            longest_streak=metrics.get('longest_streak'),
            current_streak=metrics.get('current_streak'),
            reengagement_strategy=None,
            calculated_at=datetime.utcnow()
        )

        # Get active plateaus
        stmt_plateaus = select(LearningPlateau).where(
            and_(
                LearningPlateau.user_id == current_user.id,
                LearningPlateau.is_active == True,
                LearningPlateau.resolved == False
            )
        ).order_by(LearningPlateau.detected_at.desc())

        result = await db.execute(stmt_plateaus)
        plateaus = result.scalars().all()

        active_plateaus = [
            LearningPlateauResponse(
                plateau_id=p.id,
                topic=p.topic,
                skill_id=p.skill_id,
                days_on_topic=p.days_on_topic,
                attempts=p.attempts,
                mastery_level=p.mastery_level,
                mastery_improvement=p.mastery_improvement,
                is_active=p.is_active,
                intervention_suggested=p.intervention_suggested,
                detected_at=p.detected_at
            )
            for p in plateaus
        ]

        # Get skill regressions
        stmt_regressions = select(SkillRegression).where(
            SkillRegression.user_id == current_user.id
        ).order_by(SkillRegression.detected_at.desc()).limit(5)

        result = await db.execute(stmt_regressions)
        regressions = result.scalars().all()

        skill_regressions = [
            SkillRegressionResponse(
                regression_id=r.id,
                skill_id=r.skill_id,
                skill_name=r.skill_name,
                peak_mastery=r.peak_mastery,
                current_mastery=r.current_mastery,
                regression_amount=r.regression_amount,
                days_since_practice=r.days_since_practice,
                last_practiced_at=r.last_practiced_at,
                urgency=r.urgency,
                reminder_sent=r.reminder_sent,
                detected_at=r.detected_at
            )
            for r in regressions
        ]

        # Get timing profile
        profile = await timing_optimizer.analyze_user_timing(
            current_user.id,
            db
        )

        timing_profile = TimingProfileResponse(
            user_id=current_user.id,
            peak_hours=profile.get('peak_hours', []),
            optimal_study_time=profile.get('optimal_study_time'),
            best_days=profile.get('best_days', []),
            avg_session_duration_minutes=profile.get('avg_session_duration'),
            preferred_session_length=profile.get('preferred_session_length'),
            performance_by_hour={str(k): v for k, v in profile.get('performance_by_hour', {}).items()},
            most_active_hour=profile.get('most_active_hour'),
            least_active_hour=profile.get('least_active_hour'),
            typical_study_days=profile.get('typical_study_days', []),
            sessions_analyzed=profile.get('sessions_analyzed', 0),
            confidence=profile.get('confidence', 0.0),
            updated_at=datetime.utcnow()
        )

        # Check if now is a good time
        is_good_time = await timing_optimizer.should_send_intervention_now(
            current_user.id,
            datetime.utcnow(),
            db
        )

        # Build priority actions
        priority_actions = []

        if risk_score > 0.7:
            priority_actions.append({
                "type": "critical_dropout_risk",
                "message": "User at critical risk of dropping out",
                "action": "Execute re-engagement strategy immediately"
            })

        for plateau in active_plateaus:
            if plateau.days_on_topic > 7:
                priority_actions.append({
                    "type": "learning_plateau",
                    "message": f"User stuck on {plateau.topic} for {plateau.days_on_topic} days",
                    "action": "Suggest alternative learning approach"
                })

        for regression in skill_regressions:
            if regression.urgency in ['high', 'critical']:
                priority_actions.append({
                    "type": "skill_regression",
                    "message": f"{regression.skill_name} mastery declining",
                    "action": "Schedule review session"
                })

        total_insights = len(active_plateaus) + len(skill_regressions) + (1 if risk_score > 0.5 else 0)

        return PredictiveInsightsResponse(
            user_id=current_user.id,
            dropout_risk=dropout_risk,
            active_plateaus=active_plateaus,
            skill_regressions=skill_regressions,
            timing_profile=timing_profile,
            is_good_time_now=is_good_time,
            total_insights=total_insights,
            priority_actions=priority_actions,
            generated_at=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Error getting predictive insights for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get predictive insights"
        )

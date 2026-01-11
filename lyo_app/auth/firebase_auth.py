"""
Firebase Authentication Service
Handles Firebase token verification and user authentication/registration.
"""

import logging
import os
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Check if Firebase is available
FIREBASE_AVAILABLE = False
try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    FIREBASE_AVAILABLE = True
except ImportError:
    logger.warning("Firebase Admin SDK not installed")
    firebase_admin = None
    firebase_auth = None


class FirebaseAuthService:
    """Service for Firebase authentication operations."""
    
    def __init__(self):
        self._initialized = False
        self._initialize()
    
    def _initialize(self):
        """Initialize Firebase Admin SDK if not already done."""
        if not FIREBASE_AVAILABLE:
            logger.warning("Firebase Admin SDK not available")
            return
            
        if firebase_admin._apps:
            self._initialized = True
            return
            
        try:
            from firebase_admin import credentials
            
            # Priority: Firebase credentials file > JSON env var > ADC
            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
            cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
            project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT_ID", "lyo-app")
            
            cred = None
            
            # 1. Try file-based credentials
            if cred_path and os.path.exists(cred_path):
                logger.info(f"Loading Firebase credentials from file: {cred_path}")
                cred = credentials.Certificate(cred_path)
            # 2. Try JSON environment variable
            elif cred_json:
                import json
                logger.info("Loading Firebase credentials from JSON env var")
                cred_dict = json.loads(cred_json)
                cred = credentials.Certificate(cred_dict)
            # 3. Fallback to ADC
            else:
                logger.info("Using Application Default Credentials for Firebase")
                cred = credentials.ApplicationDefault()
            
            options = {'projectId': project_id} if project_id else {}
            firebase_admin.initialize_app(cred, options=options)
            self._initialized = True
            logger.info(f"Firebase initialized with project: {project_id}")
            
        except Exception as e:
            logger.error(f"Firebase initialization failed: {e}")
            self._initialized = False
    
    def is_available(self) -> bool:
        """Check if Firebase authentication is available."""
        return FIREBASE_AVAILABLE and self._initialized
    
    async def verify_firebase_token(self, id_token: str) -> Dict[str, Any]:
        """
        Verify a Firebase ID token.
        
        CRITICAL: Supports cross-project verification where:
        - iOS app uses Firebase project 'lyo-app' (generates tokens with aud='lyo-app')
        - Backend uses service account from 'lyobackend' project
        
        Args:
            id_token: The Firebase ID token from the client
            
        Returns:
            Decoded token data containing uid, email, etc.
            
        Raises:
            ValueError: If token is invalid or expired
        """
        import os
        
        if not self.is_available():
            raise ValueError("Firebase authentication is not available")
        
        # Get the expected audience from environment (the iOS Firebase project)
        expected_audience = os.getenv("FIREBASE_PROJECT_ID", "lyo-app")
        
        try:
            # First, try standard verification
            decoded_token = firebase_auth.verify_id_token(id_token, check_revoked=True)
            return decoded_token
        except firebase_auth.ExpiredIdTokenError:
            raise ValueError("Token has expired")
        except firebase_auth.RevokedIdTokenError:
            raise ValueError("Token has been revoked")
        except Exception as e:
            error_message = str(e)
            
            # Check for audience mismatch OR permission issues (INSUFFICIENT_PERMISSION)
            # Permission errors happen when checking revocation across projects without IAM roles
            should_fallback = (
                "audience" in error_message.lower() or 
                "aud" in error_message.lower() or
                "INSUFFICIENT_PERMISSION" in error_message or
                "permission" in error_message.lower()
            )
            
            if should_fallback:
                if "permission" in error_message.lower():
                    logger.warning(f"⚠️ Permission error checking revocation: {e}. Falling back to local verification.")
                else:
                    logger.warning(f"🔄 Audience mismatch detected, attempting cross-project verification...")
                
                logger.warning(f"   Expected audience: {expected_audience}")
                
                # Try verification without audience check using Google's public keys
                try:
                    import google.auth.transport.requests
                    import google.oauth2.id_token
                    
                    # Verify using Google's public keys (validates signature and expiry)
                    request = google.auth.transport.requests.Request()
                    decoded_token = google.oauth2.id_token.verify_firebase_token(
                        id_token, 
                        request,
                        audience=expected_audience  # Use iOS project ID as audience
                    )
                    
                    # CRITICAL FIX: Ensure 'uid' is present (google.oauth2 returns 'sub')
                    if 'uid' not in decoded_token and 'sub' in decoded_token:
                        decoded_token['uid'] = decoded_token['sub']
                    
                    logger.info(f"✅ Cross-project token verification successful for uid: {decoded_token.get('uid')}")
                    return decoded_token
                    
                except Exception as cross_verify_error:
                    logger.error(f"❌ Cross-project verification also failed: {cross_verify_error}")
                    # If it was originally a permission error, raise that, otherwise raise the invalid token error
                    raise ValueError(f"Token verification failed: {str(e)}")
            
            # For other errors
            logger.error(f"Token verification failed: {e}")
            raise ValueError(f"Token verification failed: {str(e)}")
    
    async def get_user_by_firebase_uid(self, db: AsyncSession, firebase_uid: str):
        """Get user by Firebase UID."""
        from lyo_app.auth.models import User
        
        result = await db.execute(
            select(User).where(User.firebase_uid == firebase_uid)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_email(self, db: AsyncSession, email: str):
        """Get user by email."""
        from lyo_app.auth.models import User
        
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def authenticate_with_firebase(
        self, 
        db: AsyncSession, 
        id_token: str
    ) -> Tuple[Any, Any]:
        """
        Authenticate user with Firebase token.
        Creates account if user doesn't exist.
        
        Returns:
            Tuple of (user, token)
        """
        from lyo_app.auth.models import User
        from lyo_app.auth.security import create_access_token, hash_password
        from lyo_app.auth.schemas import Token
        import secrets
        
        # Verify the Firebase token
        token_data = await self.verify_firebase_token(id_token)
        
        firebase_uid = token_data.get("uid")
        email = token_data.get("email")
        name = token_data.get("name", "")
        provider = token_data.get("firebase", {}).get("sign_in_provider", "unknown")
        
        if not firebase_uid:
            raise ValueError("Invalid token: missing UID")
        
        # Try to find existing user
        user = await self.get_user_by_firebase_uid(db, firebase_uid)
        
        if not user and email:
            # Check if user exists with this email
            user = await self.get_user_by_email(db, email)
            if user:
                # Link Firebase to existing user
                user.firebase_uid = firebase_uid
                user.auth_provider = provider
                await db.commit()
        
        if not user:
            # Create new user
            # Generate a unique username from email or name
            base_username = email.split("@")[0] if email else name.replace(" ", "_").lower()
            username = base_username[:45]  # Leave room for suffix
            
            # Check username uniqueness
            existing = await db.execute(
                select(User).where(User.username == username)
            )
            if existing.scalar_one_or_none():
                username = f"{username}_{secrets.token_hex(3)}"
            
            # Parse name
            name_parts = name.split(" ", 1) if name else ["User", ""]
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            
            # Create user with random password (won't be used for Firebase auth)
            user = User(
                email=email or f"{firebase_uid}@firebase.local",
                username=username,
                hashed_password=hash_password(secrets.token_urlsafe(32)),
                first_name=first_name,
                last_name=last_name,
                firebase_uid=firebase_uid,
                auth_provider=provider,
                is_verified=True,  # Firebase verifies email
                is_active=True
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"Created new user from Firebase: {email}")
        
        
        # Create access and refresh tokens using jwt_auth module for consistency
        # with the token verification used by chat endpoints (get_optional_current_user)
        from lyo_app.auth.jwt_auth import create_access_token, create_refresh_token
        from lyo_app.auth.models import RefreshToken as RefreshTokenModel
        from lyo_app.core.settings import settings as jwt_settings
        
        access_token = create_access_token(user_id=str(user.id))
        refresh_token_str = create_refresh_token(user_id=str(user.id))
        
        # CRITICAL FIX: Store refresh token in database so /auth/refresh can validate it
        refresh_token_record = RefreshTokenModel(
            user_id=user.id,
            token=refresh_token_str,
            expires_at=datetime.utcnow() + timedelta(days=jwt_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
            is_revoked=False
        )
        db.add(refresh_token_record)
        await db.commit()
        logger.info(f"Stored refresh token for user {user.id}")
        
        # Get expiration time from settings
        expires_in = jwt_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        
        token = Token(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="bearer",
            expires_in=expires_in
        )
        
        return user, token
    
    async def link_firebase_to_user(
        self, 
        db: AsyncSession, 
        user: Any, 
        firebase_uid: str,
        provider: str
    ):
        """Link a Firebase account to an existing user."""
        user.firebase_uid = firebase_uid
        user.auth_provider = provider
        await db.commit()
        logger.info(f"Linked Firebase to user: {user.email}")


# Singleton instance
firebase_auth_service = FirebaseAuthService()

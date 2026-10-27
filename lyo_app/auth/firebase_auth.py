"""
Firebase Authentication Service
Handles Firebase token verification and user authentication/registration.
"""

import logging
import os
import re
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


APPLE_PROVIDER = "apple.com"
# "Hide My Email" addresses; Apple forwards them to the person.
APPLE_RELAY_DOMAIN = "privaterelay.appleid.com"
# Accounts with no shareable email get this stand-in address. It must pass
# email validation (".local" does not), and lyoai.app is ours, so nothing
# sent to it can reach anyone else.
PLACEHOLDER_EMAIL_DOMAIN = "users.lyoai.app"
LEGACY_PLACEHOLDER_SUFFIX = "@firebase.local"


def sign_in_provider(token_data: Dict[str, Any]) -> str:
    """How the person signed in to Firebase: apple.com, google.com, password..."""
    return (token_data.get("firebase") or {}).get("sign_in_provider") or "unknown"


def placeholder_email(firebase_uid: str) -> str:
    return f"{firebase_uid.lower()}@{PLACEHOLDER_EMAIL_DOMAIN}"


class FirebaseAuthService:
    """Service for Firebase authentication operations."""
    
    def __init__(self):
        self._initialized = False
        self._public_verification_only = False
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
            
            # Priority: Firebase credentials file > JSON env var.
            # Do not fall back to Application Default Credentials on Railway: ADC
            # probes GCP metadata endpoints and can stall /auth/firebase requests.
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
            else:
                logger.warning("No explicit Firebase credentials configured; using public ID-token verification only")
                self._public_verification_only = True
                self._initialized = False
                return
            
            # FORCE project_id to 'lyo-app' if not provided to avoid "A project ID is required" errors
            active_project_id = project_id or "lyo-app"
            os.environ["GOOGLE_CLOUD_PROJECT"] = active_project_id
            options = {'projectId': active_project_id}
            
            try:
                firebase_admin.initialize_app(cred, options=options)
                self._initialized = True
                logger.info(f"Firebase initialized with project: {project_id}")
            except Exception as init_err:
                logger.error(f"Failed to initialize firebase_admin: {init_err}")
                self._initialized = False
            
        except Exception as e:
            logger.error(f"Firebase initialization failed: {e}")
            self._initialized = False
    
    def is_available(self) -> bool:
        """Check if Firebase authentication is available."""
        return FIREBASE_AVAILABLE and (self._initialized or self._public_verification_only)

    def _verify_token_with_public_keys(self, id_token: str, expected_audience: str) -> Dict[str, Any]:
        """Verify a Firebase ID token using Google's public certificates."""
        import google.auth.transport.requests
        import google.oauth2.id_token

        request = google.auth.transport.requests.Request()
        decoded_token = google.oauth2.id_token.verify_firebase_token(
            id_token,
            request,
            audience=expected_audience,
        )
        if 'uid' not in decoded_token and 'sub' in decoded_token:
            decoded_token['uid'] = decoded_token['sub']
        return decoded_token
    
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

        if self._public_verification_only:
            try:
                return self._verify_token_with_public_keys(id_token, expected_audience)
            except Exception as e:
                logger.error(f"Token verification failed: {e}")
                raise ValueError(f"Token verification failed: {str(e)}")
        
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
            
            # Check for audience mismatch OR permission issues OR missing project ID
            should_fallback = (
                "audience" in error_message.lower() or 
                "aud" in error_message.lower() or
                "INSUFFICIENT_PERMISSION" in error_message or
                "permission" in error_message.lower() or
                "credential" in error_message.lower() or
                "project id" in error_message.lower() or
                "app" in error_message.lower()
            )
            
            if should_fallback:
                if "permission" in error_message.lower():
                    logger.warning(f"⚠️ Permission error checking revocation: {e}. Falling back to local verification.")
                else:
                    logger.warning(f"🔄 Audience mismatch detected, attempting cross-project verification...")
                
                logger.warning(f"   Expected audience: {expected_audience}")
                
                # Try verification without audience check using Google's public keys
                try:
                    decoded_token = self._verify_token_with_public_keys(id_token, expected_audience)
                    
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
    
    async def find_or_create_user(self, db: AsyncSession, token_data: Dict[str, Any]) -> Tuple[Any, bool]:
        """The account a verified Firebase token signs in to, and whether it is new.

        An account already linked to the Firebase uid always signs in by it.
        Otherwise a confirmed email opens the account that has it (and links
        it); an unconfirmed one neither opens nor creates an account, because
        anyone can make a Firebase account with someone else's email.

        Sign in with Apple is the exception to refusing: Apple users cannot
        confirm an email with us, and may hide it, share a private-relay
        address, or (on later sign-ins) send none at all, and Apple sends no
        name to the server. An Apple sign-in therefore always gets an account,
        keyed by its Firebase uid; it only claims an email Firebase confirmed.
        """
        from lyo_app.auth.models import User
        from lyo_app.auth.security import hash_password
        import secrets

        firebase_uid = token_data.get("uid")
        if not firebase_uid:
            raise ValueError("Invalid token: missing UID")
        provider = sign_in_provider(token_data)

        user = await self.get_user_by_firebase_uid(db, firebase_uid)
        if user:
            if user.email and user.email.endswith(LEGACY_PLACEHOLDER_SUFFIX):
                # The old stand-in address fails email validation, so the
                # account could not be returned to the app at all.
                user.email = placeholder_email(firebase_uid)
                await db.commit()
            return user, False

        email = (token_data.get("email") or "").strip() or None
        if email and not token_data.get("email_verified"):
            if provider != APPLE_PROVIDER:
                raise ValueError("Confirm your email address before signing in with it")
            email = None

        if email:
            user = await self.get_user_by_email(db, email)
            if user:
                user.firebase_uid = firebase_uid
                user.auth_provider = provider
                await db.commit()
                return user, False

        name = (token_data.get("name") or "").strip()
        name_parts = name.split(" ", 1) if name else ["User", ""]
        user = User(
            email=email or placeholder_email(firebase_uid),
            username=await self._unique_username(db, email, name, firebase_uid),
            # Random password: this account signs in through Firebase.
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            first_name=name_parts[0],
            last_name=name_parts[1] if len(name_parts) > 1 else "",
            firebase_uid=firebase_uid,
            auth_provider=provider,
            is_verified=bool(email),
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("Created user %s from Firebase (%s)", user.id, provider)
        return user, True

    async def _unique_username(self, db: AsyncSession, email: Optional[str], name: str, firebase_uid: str) -> str:
        from lyo_app.auth.models import User
        import secrets

        if email and not email.lower().endswith("@" + APPLE_RELAY_DOMAIN):
            base = email.split("@", 1)[0]
        else:
            # A relay address's local part is random; prefer the name.
            base = name or "learner"
        base = re.sub(r"[^a-z0-9_.]+", "_", base.lower()).strip("_.")[:40]
        if len(base) < 3:
            base = "learner"
        username = base
        while (await db.execute(select(User.id).where(User.username == username))).first():
            username = f"{base}_{secrets.token_hex(3)}"
        return username

    async def issue_tokens(self, db: AsyncSession, user: Any):
        """Backend access and refresh tokens for ``user``; the refresh token is stored."""
        from lyo_app.auth.jwt_auth import create_access_token, create_refresh_token
        from lyo_app.auth.models import RefreshToken as RefreshTokenModel
        from lyo_app.auth.schemas import Token
        from lyo_app.core.settings import settings as jwt_settings

        # jwt_auth tokens are the ones every route's verification accepts.
        access_token = create_access_token(user_id=str(user.id))
        refresh_token_str = create_refresh_token(user_id=str(user.id))
        # Stored so /auth/refresh can validate (and account deletion revoke) it.
        db.add(RefreshTokenModel(
            user_id=user.id,
            token=refresh_token_str,
            expires_at=datetime.utcnow() + timedelta(days=jwt_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
            is_revoked=False
        ))
        await db.commit()
        return Token(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="bearer",
            expires_in=jwt_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

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
        token_data = await self.verify_firebase_token(id_token)
        user, _is_new = await self.find_or_create_user(db, token_data)
        return user, await self.issue_tokens(db, user)
    
    def delete_firebase_user(self, firebase_uid: str) -> bool:
        """Delete the Firebase account (blocking). True if it is gone.

        Needs service-account credentials (FIREBASE_CREDENTIALS_JSON or
        FIREBASE_CREDENTIALS_PATH) with permission on the app's Firebase
        project; public-key verification alone cannot delete anyone.
        """
        if not (FIREBASE_AVAILABLE and self._initialized):
            logger.error(
                "Firebase user %s was not deleted: Firebase Admin credentials are not configured",
                firebase_uid,
            )
            return False
        try:
            firebase_auth.delete_user(firebase_uid)
        except firebase_auth.UserNotFoundError:
            pass
        except Exception:
            logger.exception("Firebase user %s could not be deleted", firebase_uid)
            return False
        logger.info("Deleted Firebase user %s", firebase_uid)
        return True

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

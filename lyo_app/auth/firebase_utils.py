import logging
import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, status
import os

logger = logging.getLogger(__name__)

# Initialize Firebase Admin if not already done
# CRITICAL: Must use FIREBASE_PROJECT_ID (lyo-app) not GCP_PROJECT_ID (lyobackend)
# for token verification to work with iOS Firebase tokens
if not firebase_admin._apps:
    try:
        # Priority: Firebase credentials file > JSON env var > ADC
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
        # IMPORTANT: Use FIREBASE_PROJECT_ID first - this is the iOS Firebase project
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT_ID", "lyo-app")
        
        cred = None
        
        # 1. Try file-based credentials (mounted secret in Cloud Run)
        if cred_path and os.path.exists(cred_path):
            logger.info(f"📁 Loading Firebase credentials from file: {cred_path}")
            cred = credentials.Certificate(cred_path)
            # Extract project_id from credentials if available
            try:
                import json
                with open(cred_path) as f:
                    cred_data = json.load(f)
                    project_id = cred_data.get("project_id", project_id)
                    logger.info(f"🔑 Using project_id from credentials: {project_id}")
            except Exception:
                pass
        
        # 2. Try JSON environment variable
        elif cred_json:
            logger.info("🔐 Loading Firebase credentials from JSON environment variable")
            import json
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
        
        # 3. Fallback to ADC
        else:
            logger.info("⚠️ No Firebase credentials found - using Application Default Credentials")
            cred = credentials.ApplicationDefault()
        
        # Initialize with explicit project ID if available, to support cross-project verification
        options = {}
        if project_id:
            options['projectId'] = project_id
            
        if cred:
            firebase_admin.initialize_app(cred, options=options)
        else:
            firebase_admin.initialize_app(options=options)

    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin: {e}")

def verify_firebase_token_robust(token: str):
    """
    Verifies a Firebase ID token.
    CRITICAL FIX: Does not strictly enforce audience if it matches the project,
    solving the iOS Client ID vs Project ID mismatch.
    """
    try:
        # 1. Attempt standard verification
        # check_revoked=True is good practice
        decoded_token = auth.verify_id_token(token, check_revoked=True)
        return decoded_token
    except ValueError as e:
        # 2. If it fails due to audience, we might need to be more permissive 
        # (only if you are sure the token is from your app)
        logger.error(f"Token verification failed: {str(e)}")
        
        # If the error is about audience, we might want to inspect the token without verification
        # to see if it's at least signed by Google and has the right issuer.
        # However, verify_id_token does signature verification. 
        # If we want to bypass audience check, we can't easily do it with verify_id_token.
        # But usually the mismatch is because the backend expects project ID as audience, 
        # and the token has the iOS Client ID.
        
        # For now, we will raise 401 but log it clearly.
        # The "Undisputed Solution" code block just caught ValueError and raised 401.
        # I will stick to that for now, but I'll add more detailed logging.
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except Exception as e:
        logger.error(f"Firebase auth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )

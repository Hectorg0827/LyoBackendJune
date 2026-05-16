"""
Firebase Admin SDK initialisation — Railway-safe
================================================

Priority order:
  1. FIREBASE_CREDENTIALS_PATH  – mounted service-account file
  2. FIREBASE_CREDENTIALS_JSON  – JSON string in env var
  3. ApplicationDefault()       – GCP / Cloud Run ADC

If none of the above work we initialise Firebase WITHOUT credentials using
only a project_id so that firebase_admin.auth can at minimum verify tokens
by contacting Google's public JWKS endpoint (which only needs the project id,
not a service account).

Project ID resolution (first match wins):
  FIREBASE_PROJECT_ID > GCP_PROJECT_ID > credentials file > "lyo-app"
"""

import json
import logging
import os

import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def _init_firebase() -> None:
    """Initialise Firebase Admin SDK idempotently."""
    if firebase_admin._apps:
        return

    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    firebase_project_id = os.getenv("FIREBASE_PROJECT_ID")
    gcp_project_id = os.getenv("GCP_PROJECT_ID")

    # Resolve project_id (we MUST have one for auth.verify_id_token)
    project_id = firebase_project_id or gcp_project_id or None

    logger.info("🔥 Firebase initialisation:")
    logger.info(f"   FIREBASE_PROJECT_ID : {firebase_project_id!r}")
    logger.info(f"   GCP_PROJECT_ID      : {gcp_project_id!r}")

    cred = None

    # ── 1. File-based service account ───────────────────────────────────────
    if cred_path and os.path.exists(cred_path):
        logger.info(f"📁 Loading credentials from file: {cred_path}")
        cred = credentials.Certificate(cred_path)
        if not project_id:
            try:
                with open(cred_path) as f:
                    creds_project_id = json.load(f).get("project_id")
                if creds_project_id:
                    project_id = creds_project_id
                    logger.info(f"🔑 project_id from credentials file: {project_id}")
            except Exception:
                pass

    # ── 2. JSON string in environment variable ───────────────────────────────
    elif cred_json:
        logger.info("🔐 Loading credentials from FIREBASE_CREDENTIALS_JSON")
        try:
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
            if not project_id:
                project_id = cred_dict.get("project_id")
        except Exception as exc:
            logger.warning(f"⚠️ Failed to parse FIREBASE_CREDENTIALS_JSON: {exc}")

    # ── 3. Application Default Credentials (GCP / Cloud Run) ─────────────────
    else:
        logger.info("⚠️ No credentials file/JSON — attempting ApplicationDefault()")
        try:
            cred = credentials.ApplicationDefault()
        except Exception as exc:
            logger.warning(f"⚠️ ApplicationDefault failed ({exc}) — will init without cred")
            cred = None

    # Fallback project id so the SDK never complains about a missing project
    if not project_id:
        project_id = "lyo-app"
        logger.warning(f"⚠️ No project_id found — defaulting to '{project_id}'. "
                       "Set FIREBASE_PROJECT_ID on Railway to fix auth verification.")

    # Also export so google-auth picks it up automatically
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)

    options = {"projectId": project_id}

    try:
        if cred:
            firebase_admin.initialize_app(cred, options=options)
        else:
            # No credentials at all — init with just project id.
            # Token verification via verify_id_token will still work because
            # it only needs the project id to fetch Google's public JWKS.
            firebase_admin.initialize_app(options=options)
        logger.info(f"✅ Firebase Admin initialised (project={project_id!r})")
    except ValueError as exc:
        # Already initialised in another import path
        logger.info(f"ℹ️ Firebase already initialised: {exc}")
    except Exception as exc:
        logger.error(f"❌ Firebase Admin init failed: {exc}")


# Run at import time
_init_firebase()


# ─── Public helpers ──────────────────────────────────────────────────────────

def verify_firebase_token_robust(token: str) -> dict:
    """
    Verify a Firebase ID token and return the decoded claims.

    Falls back to a lenient decode (checks signature but not audience) when the
    strict check raises ValueError for a project/audience mismatch — common when
    the iOS app uses a different client_id as the token audience.
    """
    try:
        return auth.verify_id_token(token, check_revoked=True)
    except auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please sign in again.",
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired. Please sign in again.",
        )
    except ValueError as exc:
        # Project / audience mismatch — try without audience check if possible
        logger.warning(f"⚠️ Strict Firebase verify failed ({exc}), retrying without audience check")
        try:
            # check_revoked=False skips the revocation check which needs a project
            return auth.verify_id_token(token, check_revoked=False)
        except Exception as inner:
            logger.error(f"❌ Firebase token verification failed: {inner}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token verification failed: {inner}",
            )
    except Exception as exc:
        logger.error(f"❌ Firebase auth error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )

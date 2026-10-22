"""Firebase Admin SDK integration.
Provides optional Firestore & Storage helpers when Firebase credentials are present.
"""
from __future__ import annotations
import os
import re
from typing import Optional, Any, Dict

try:
    import firebase_admin  # type: ignore
    from firebase_admin import credentials, firestore, storage
    _FIREBASE_AVAILABLE = True
except Exception:  # pragma: no cover - guarded import
    _FIREBASE_AVAILABLE = False

def _is_isolated_staging_project(project_id: str | None, credential_project: str | None,
                                 gcp_project: str | None = None) -> bool:
    """Allow staging writes only to a named test project matching the key."""
    return bool(
        isinstance(project_id, str)
        and re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project_id)
        and re.search(r"(?:^|-)(?:staging|test|sandbox)(?:-|$)", project_id)
        and credential_project == project_id
        and (not gcp_project or gcp_project == project_id)
    )


class FirebaseClient:
    _instance: Optional["FirebaseClient"] = None

    def __new__(cls):  # singleton
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._initialized_sdk = False
        self.enabled = False
        self.db = None
        self.bucket = None

    def initialize_app(self):
        """Initialize optional Firebase storage, failing closed in staging."""
        if self._initialized_sdk:
            return
        self._initialized_sdk = True
        if not _FIREBASE_AVAILABLE:
            return

        try:
            firebase_project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT_ID")
            gcp_project_id = os.getenv("GCP_PROJECT_ID")
            cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            staging = os.getenv("ENVIRONMENT", "").strip().lower() == "staging"

            # Never use ADC / metadata-server discovery or a different
            # Firebase project for synthetic artifact writes in staging.
            if staging:
                if not cred_json and not (cred_path and os.path.isfile(cred_path)):
                    return
                import json
                if cred_json:
                    certificate = json.loads(cred_json)
                else:
                    with open(cred_path, encoding="utf-8") as handle:
                        certificate = json.load(handle)
                if not _is_isolated_staging_project(firebase_project_id, certificate.get("project_id"), gcp_project_id):
                    return

            if cred_json:
                import json
                cred = credentials.Certificate(json.loads(cred_json))
            elif cred_path and os.path.isfile(cred_path):
                cred = credentials.Certificate(cred_path)
            else:
                # Preserve existing production behavior; staging returned
                # above rather than selecting environment-default credentials.
                cred = credentials.ApplicationDefault()

            try:
                app = firebase_admin.get_app()
            except ValueError:
                app = firebase_admin.initialize_app(cred, {
                    "projectId": firebase_project_id,
                    "storageBucket": f"{gcp_project_id}.appspot.com" if gcp_project_id else None,
                })
            if staging and app.project_id != firebase_project_id:
                return

            self.db = firestore.client(app=app)
            try:
                self.bucket = storage.bucket(app=app)
            except Exception:
                self.bucket = None
            self.enabled = True
        except Exception:
            self.enabled = False

    def is_enabled(self) -> bool:
        return self.enabled

    def save_conversation(self, session_id: str, data: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        try:
            self.db.collection("ai_conversations").document(session_id).set(data)
            return True
        except Exception:
            return False

    def upload_file(self, local_path: str, dest_path: str) -> Optional[str]:
        if not self.enabled or not getattr(self, "bucket", None):
            return None
        try:
            blob = self.bucket.blob(dest_path)
            blob.upload_from_filename(local_path)
            blob.make_public()
            return blob.public_url
        except Exception:
            return None

firebase_client = FirebaseClient()


def get_firebase_manager():
    """Get Firebase client instance"""
    return firebase_client

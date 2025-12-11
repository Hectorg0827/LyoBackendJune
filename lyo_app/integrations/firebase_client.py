"""Firebase Admin SDK integration.
Provides optional Firestore & Storage helpers when Firebase credentials are present.
"""
from __future__ import annotations
import os
from typing import Optional, Any, Dict

try:
    import firebase_admin  # type: ignore
    from firebase_admin import credentials, firestore, storage
    _FIREBASE_AVAILABLE = True
except Exception:  # pragma: no cover - guarded import
    _FIREBASE_AVAILABLE = False

class FirebaseClient:
    _instance: Optional["FirebaseClient"] = None

    def __new__(cls):  # singleton
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):  # already init
            return
        self._initialized = True
        self.enabled = False
        if not _FIREBASE_AVAILABLE:
            return
        try:
            # Use FIREBASE_PROJECT_ID for auth, GCP_PROJECT_ID for storage
            firebase_project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT_ID")
            gcp_project_id = os.getenv("GCP_PROJECT_ID")
            
            # Priority: FIREBASE_CREDENTIALS_JSON > GOOGLE_APPLICATION_CREDENTIALS > ADC
            cred: Any
            cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
            
            if cred_json:
                # Use Firebase-specific credentials from JSON env var
                import json
                cred_dict = json.loads(cred_json)
                cred = credentials.Certificate(cred_dict)
            elif os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and os.path.exists(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")):
                cred = credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
            else:
                cred = credentials.ApplicationDefault()
            
            # Initialize with Firebase project ID for token verification
            firebase_admin.initialize_app(cred, {
                "projectId": firebase_project_id,
                "storageBucket": f"{gcp_project_id}.appspot.com" if gcp_project_id else None
            })
            self.db = firestore.client()
            try:
                self.bucket = storage.bucket()
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

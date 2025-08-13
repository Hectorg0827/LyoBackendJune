"""Google Cloud Secret Manager integration utilities.
Provides secure retrieval of secrets when running on GCP / Cloud Run.
"""
from __future__ import annotations
import os
from functools import lru_cache
from typing import Optional

try:
    from google.cloud import secretmanager  # type: ignore
    _GCP_AVAILABLE = True
except Exception:  # pragma: no cover - import guarded
    _GCP_AVAILABLE = False

SECRET_PROJECT_ENV = "GCP_PROJECT_ID"

class SecretManagerClient:
    def __init__(self, project_id: Optional[str]):
        self.project_id = project_id
        if _GCP_AVAILABLE and project_id:
            try:
                self._client = secretmanager.SecretManagerServiceClient()
            except Exception:  # pragma: no cover
                self._client = None
        else:
            self._client = None

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        if not self._client or not self.project_id:
            return os.getenv(name, default)
        secret_path = f"projects/{self.project_id}/secrets/{name}/versions/latest"
        try:
            version = self._client.access_secret_version(name=secret_path)
            return version.payload.data.decode("utf-8")
        except Exception:
            return os.getenv(name, default)

@lru_cache(maxsize=1)
def get_secret_manager() -> SecretManagerClient:
    return SecretManagerClient(os.getenv(SECRET_PROJECT_ENV))


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Fetch a secret value, falling back to environment variable/local default."""
    return get_secret_manager().get(name, default)

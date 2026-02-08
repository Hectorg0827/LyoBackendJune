import logging
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from lyo_app.integrations.firebase_client import firebase_client
from lyo_app.ai.schemas.lyo2 import ArtifactType

logger = logging.getLogger(__name__)

class ArtifactService:
    """
    Manages Lyo 2.0 artifacts with append-only versioning.
    Backed by Firestore.
    """
    
    COLLECTION = "lyo_artifacts"
    
    def __init__(self):
        self.fb = firebase_client
        self.fb.initialize_app()
        
    def _is_enabled(self) -> bool:
        return self.fb.enabled and self.fb.db is not None

    async def create_artifact(self, user_id: str, artifact_type: ArtifactType, content: Dict[str, Any], metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Creates a new artifact (v1).
        """
        artifact_id = str(uuid.uuid4())
        version = 1
        
        doc_data = {
            "artifact_id": artifact_id,
            "user_id": user_id,
            "type": artifact_type.value,
            "version": version,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if self._is_enabled():
            # Store versioned document: lyo_artifacts/{artifact_id}_v{version}
            doc_ref = self.fb.db.collection(self.COLLECTION).document(f"{artifact_id}_v{version}")
            doc_ref.set(doc_data)
        else:
            logger.warning("Firebase not enabled, artifact not persisted")
            
        return doc_data

    async def update_artifact(self, artifact_id: str, new_content: Dict[str, Any], metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Creates a new version of an existing artifact.
        """
        # 1. Find latest version
        latest_version = await self.get_latest_version_number(artifact_id)
        new_version = latest_version + 1
        
        # 2. Get base data from latest version if needed (simplified for now)
        # In a real app, we might want to fetch the previous version to merge metadata
        
        doc_data = {
            "artifact_id": artifact_id,
            "version": new_version,
            "content": new_content,
            "metadata": metadata or {},
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if self._is_enabled():
            doc_ref = self.fb.db.collection(self.COLLECTION).document(f"{artifact_id}_v{new_version}")
            # Get existing doc to preserve user_id and type
            prev_doc = self.fb.db.collection(self.COLLECTION).document(f"{artifact_id}_v{latest_version}").get()
            if prev_doc.exists:
                prev_data = prev_doc.to_dict()
                doc_data["user_id"] = prev_data.get("user_id")
                doc_data["type"] = prev_data.get("type")
                doc_data["created_at"] = prev_data.get("created_at")
            
            doc_ref.set(doc_data)
        else:
            logger.warning("Firebase not enabled, artifact version not persisted")
            
        return doc_data

    async def get_latest_version_number(self, artifact_id: str) -> int:
        """
        Retrieves the latest version number for an artifact.
        """
        if not self._is_enabled():
            return 1
            
        # Query Firestore for latest version
        docs = self.fb.db.collection(self.COLLECTION)\
            .where("artifact_id", "==", artifact_id)\
            .order_by("version", direction="DESCENDING")\
            .limit(1)\
            .stream()
            
        for doc in docs:
            return doc.to_dict().get("version", 1)
            
        return 1

    async def get_artifact(self, artifact_id: str, version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves a specific version of an artifact, or the latest if version is None.
        """
        if not self._is_enabled():
            return None
            
        if version:
            doc_ref = self.fb.db.collection(self.COLLECTION).document(f"{artifact_id}_v{version}")
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else None
        else:
            # Get latest
            docs = self.fb.db.collection(self.COLLECTION)\
                .where("artifact_id", "==", artifact_id)\
                .order_by("version", direction="DESCENDING")\
                .limit(1)\
                .stream()
            for doc in docs:
                return doc.to_dict()
        return None

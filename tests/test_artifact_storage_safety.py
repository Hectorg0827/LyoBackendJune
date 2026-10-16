"""Exercise the storage adapter itself, including the disabled-backend boundary."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lyo_app.ai.schemas.lyo2 import ArtifactType
from lyo_app.services.artifact_service import ArtifactService


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update", "get", "version"])
async def test_disabled_storage_never_pretends_to_save_or_read(operation):
    from lyo_app.services.artifact_service import ArtifactStorageUnavailable

    service = ArtifactService.__new__(ArtifactService)
    service.fb = SimpleNamespace(enabled=False, db=None)
    calls = {
        "create": lambda: service.create_artifact("42", ArtifactType.FLASHCARDS, {"cards": []}),
        "update": lambda: service.update_artifact("deck", {"cards": []}),
        "get": lambda: service.get_artifact("deck"),
        "version": lambda: service.get_latest_version_number("deck"),
    }
    with pytest.raises(ArtifactStorageUnavailable):
        await calls[operation]()


@pytest.mark.asyncio
async def test_create_waits_for_write_and_round_trips_through_the_storage_adapter():
    saved = {}
    document = Mock()
    document.set.side_effect = lambda data: saved.update(deepcopy(data))
    document.get.side_effect = lambda: SimpleNamespace(exists=bool(saved), to_dict=lambda: deepcopy(saved))
    collection = Mock()
    collection.document.return_value = document
    service = ArtifactService.__new__(ArtifactService)
    service.fb = SimpleNamespace(enabled=True, db=Mock())
    service.fb.db.collection.return_value = collection

    content = {"cards": [{"front": "Light pigment?", "back": "Chlorophyll"}]}
    created = await service.create_artifact("42", ArtifactType.FLASHCARDS, content)
    assert saved == created
    assert await service.get_artifact(created["artifact_id"], version=1) == created
    document.set.assert_called_once()


@pytest.mark.asyncio
async def test_write_failure_cannot_return_a_created_artifact():
    service = ArtifactService.__new__(ArtifactService)
    service.fb = SimpleNamespace(enabled=True, db=Mock())
    service.fb.db.collection.return_value.document.return_value.set.side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError, match="write failed"):
        await service.create_artifact("42", ArtifactType.FLASHCARDS, {"cards": []})

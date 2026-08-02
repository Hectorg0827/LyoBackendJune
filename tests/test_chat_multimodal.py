import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from lyo_app.ai import multimodal
from lyo_app.ai.multimodal import (
    canonical_message_content,
    load_media_attachments,
    recent_media_refs,
)
from lyo_app.ai.schemas.lyo2 import InputModality, MediaRef, RouterRequest


def _image_ref(uri: str = "/api/v1/media/file/chat/example.png") -> MediaRef:
    return MediaRef(
        modality=InputModality.IMAGE,
        uri=uri,
        mime_type="image/png",
        name="worksheet.png",
        size_bytes=8,
    )


def test_router_request_accepts_document_media() -> None:
    request = RouterRequest(
        text=None,
        media=[
            MediaRef(
                modality=InputModality.DOCUMENT,
                uri="/api/v1/media/file/chat/notes.pdf",
                mime_type="application/pdf",
                name="notes.pdf",
            )
        ],
    )

    assert request.media[0].modality == InputModality.DOCUMENT


def test_canonical_message_content_preserves_attachment_for_history() -> None:
    content = canonical_message_content("What does this graph show?", [_image_ref()])

    assert content == (
        "What does this graph show?\n\n"
        "![worksheet.png](/api/v1/media/file/chat/example.png)"
    )


def test_recent_media_refs_recovers_latest_user_attachment() -> None:
    refs = recent_media_refs(
        [
            {"role": "user", "content": "![old](/api/v1/media/file/chat/old.png)"},
            {"role": "assistant", "content": "I can see it."},
            {
                "role": "user",
                "content": "Notes\n\n[📎 chapter.csv](/api/v1/media/file/chat/chapter.csv)",
            },
            {"role": "assistant", "content": "What should we inspect?"},
            {"role": "user", "content": "Explain the second row."},
        ]
    )

    assert len(refs) == 1
    assert refs[0].modality == InputModality.DOCUMENT
    assert refs[0].mime_type == "text/csv"
    assert refs[0].name == "chapter.csv"


def test_recent_media_refs_ignores_external_markdown() -> None:
    refs = recent_media_refs(
        [{"role": "user", "content": "![remote](https://example.com/image.png)"}]
    )

    assert refs == []


@pytest.mark.asyncio
async def test_load_media_attachment_returns_inline_gemini_part(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        multimodal,
        "settings",
        SimpleNamespace(upload_dir=str(tmp_path)),
    )
    media_dir = tmp_path / "media" / "chat"
    media_dir.mkdir(parents=True)
    payload = b"fake-png"
    (media_dir / "example.png").write_bytes(payload)

    parts = await load_media_attachments([_image_ref()])

    assert parts == [
        {
            "type": "media_base64",
            "mime_type": "image/png",
            "data": base64.b64encode(payload).decode("ascii"),
            "name": "worksheet.png",
        }
    ]


@pytest.mark.asyncio
async def test_load_media_attachment_rejects_arbitrary_remote_url() -> None:
    with pytest.raises(HTTPException) as error:
        await load_media_attachments([_image_ref("https://example.com/private.png")])

    assert error.value.status_code == 400
    assert "uploaded through Lyo" in error.value.detail


@pytest.mark.asyncio
async def test_load_media_attachment_limits_count() -> None:
    with pytest.raises(HTTPException) as error:
        await load_media_attachments([_image_ref()] * 5)

    assert error.value.status_code == 400
    assert "at most 4" in error.value.detail


@pytest.mark.asyncio
async def test_missing_historical_attachment_is_skipped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        multimodal,
        "settings",
        SimpleNamespace(upload_dir=str(tmp_path)),
    )

    assert await load_media_attachments([_image_ref()], missing_ok=True) == []

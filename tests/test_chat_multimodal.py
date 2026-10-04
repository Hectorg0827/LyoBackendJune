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
from lyo_app.core.ai_resilience import _openai_compatible_messages
from lyo_app.teaching_runtime.model_router import provider_order_for_tier


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


@pytest.mark.asyncio
@pytest.mark.parametrize("folder", ["test-prep", "classroom"])
async def test_shared_learning_surfaces_can_load_their_uploaded_documents(
    tmp_path, monkeypatch, folder
) -> None:
    monkeypatch.setattr(
        multimodal,
        "settings",
        SimpleNamespace(upload_dir=str(tmp_path)),
    )
    media_dir = tmp_path / "media" / folder
    media_dir.mkdir(parents=True)
    payload = b"Chapter 4: cellular respiration"
    (media_dir / "notes.txt").write_bytes(payload)

    parts = await load_media_attachments(
        [
            MediaRef(
                modality=InputModality.DOCUMENT,
                uri=f"/api/v1/media/file/{folder}/notes.txt",
                mime_type="text/plain",
                name="notes.txt",
            )
        ]
    )

    assert len(parts) == 1
    assert parts[0]["mime_type"] == "text/plain"
    assert parts[0]["extracted_text"] == payload.decode()


def test_openai_adapter_preserves_images_and_uses_extracted_document_text() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze these."},
                {
                    "type": "media_base64",
                    "mime_type": "image/png",
                    "data": "ZmFrZS1wbmc=",
                    "name": "graph.png",
                },
                {
                    "type": "media_base64",
                    "mime_type": "application/pdf",
                    "data": "ZmFrZS1wZGY=",
                    "name": "lease.pdf",
                    "extracted_text": "Monthly rent is $2,100.",
                },
            ],
        }
    ]

    normalized = _openai_compatible_messages(messages)
    parts = normalized[0]["content"]

    assert parts[0] == {"type": "text", "text": "Analyze these."}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert parts[2]["type"] == "text"
    assert "lease.pdf" in parts[2]["text"]
    assert "Monthly rent is $2,100." in parts[2]["text"]


def test_multimodal_teaching_has_more_than_one_provider() -> None:
    order = provider_order_for_tier("teaching", has_media=True)

    assert order[0] == "gpt-4o-mini"
    assert "gemini-2.5-flash" in order
    assert len(order) >= 2



@pytest.mark.asyncio
async def test_pdf_attachment_preserves_page_level_grounding(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        multimodal,
        "settings",
        SimpleNamespace(upload_dir=str(tmp_path)),
    )
    media_dir = tmp_path / "media" / "chat"
    media_dir.mkdir(parents=True)

    from pypdf import PdfWriter

    pdf_path = media_dir / "pages.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    parts = await load_media_attachments(
        [
            MediaRef(
                modality=InputModality.DOCUMENT,
                uri="/api/v1/media/file/chat/pages.pdf",
                mime_type="application/pdf",
                name="pages.pdf",
            )
        ]
    )

    assert len(parts) == 1
    assert parts[0]["mime_type"] == "application/pdf"
    # Blank PDFs remain valid native multimodal inputs. Page metadata is only
    # emitted when text extraction has something honest to cite.
    assert "source_pages" not in parts[0]


@pytest.mark.asyncio
async def test_text_attachment_exposes_grounding_page(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        multimodal,
        "settings",
        SimpleNamespace(upload_dir=str(tmp_path)),
    )
    media_dir = tmp_path / "media" / "chat"
    media_dir.mkdir(parents=True)
    (media_dir / "notes.txt").write_text("Chapter 1: Cells", encoding="utf-8")

    parts = await load_media_attachments(
        [
            MediaRef(
                modality=InputModality.DOCUMENT,
                uri="/api/v1/media/file/chat/notes.txt",
                mime_type="text/plain",
                name="notes.txt",
            )
        ]
    )

    assert parts[0]["source_pages"] == [{"page": 1, "text": "Chapter 1: Cells"}]
    assert parts[0]["page_count"] == 1

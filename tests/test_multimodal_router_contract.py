"""Regression contract for the Lyo 2.0 multimodal router."""

from lyo_app.ai.router import MultimodalRouter
from lyo_app.ai.schemas.lyo2 import RouterRequest


def test_build_prompt_accepts_media_attachments_forwarded_by_base_agent():
    """BaseAgent.execute forwards every kwarg to build_prompt.

    The streaming route calls MultimodalRouter.route with media_attachments,
    so build_prompt must accept that kwarg even though the attachments are
    passed to the model separately.
    """
    router = object.__new__(MultimodalRouter)
    request = RouterRequest(text="Hi")

    prompt = router.build_prompt(
        request=request,
        media_attachments=[
            {
                "type": "image",
                "data": "diagnostic",
                "mime_type": "image/jpeg",
            }
        ],
    )

    assert "USER TEXT: Hi" in prompt

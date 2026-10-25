"""Guard LYO course-generation defaults against restricted Gemini models."""

from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelManager


def test_multi_agent_model_tiers_use_current_gemini() -> None:
    models = {config.model_name for config in ModelManager.MODELS.values()}
    assert models == {"gemini-3.8-flash"}

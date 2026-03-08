import sys

print("1. Importing ai_resilience_manager...", flush=True)
from lyo_app.core.ai_resilience import ai_resilience_manager

print("2. Importing settings...", flush=True)
from lyo_app.core.config import settings

print("3. Importing get_current_user, get_db...", flush=True)
from lyo_app.auth.dependencies import get_current_user, get_db

print("4. Importing User...", flush=True)
from lyo_app.auth.models import User

print("5. Importing PersonalizationEngine...", flush=True)
from lyo_app.personalization.service import PersonalizationEngine

print("6. Importing A2ACourseRequest...", flush=True)
from lyo_app.ai_agents.a2a.schemas import Artifact, ArtifactType, A2ACourseRequest

print("7. Importing A2AOrchestrator...", flush=True)
from lyo_app.ai_agents.a2a.orchestrator import A2AOrchestrator

print("8. Importing ChatResponseV2...", flush=True)
from lyo_app.chat.a2ui_recursive import ChatResponseV2, UIComponent, migrate_legacy_content_types

print("9. Importing ResponseAssembler...", flush=True)
from lyo_app.chat.assembler import ResponseAssembler

print("10. Importing chat_a2ui_service...", flush=True)
from lyo_app.chat.a2ui_integration import chat_a2ui_service

print("11. Importing a2ui...", flush=True)
from lyo_app.a2ui.a2ui_generator import a2ui

print("Done with all imports!", flush=True)

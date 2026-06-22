"""LLM provider implementations for agent scaffolding."""

from src.core.config import settings
from src.domain.services.agent_service import LLMProvider


class StubLLMProvider(LLMProvider):
    """Placeholder provider that returns a deterministic message."""

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        system_prefix = f"[System: {system}] " if system else ""
        return (
            f"{system_prefix}This is a stubbed agent response. Replace the provider to call "
            f"your chosen LLM (provider={settings.llm_provider}, model={settings.llm_model}). "
            f'Original prompt: "{prompt}"'
        )


def get_llm_provider() -> LLMProvider:
    # Extend here to branch on settings.llm_provider (e.g., openai, anthropic, local).
    return StubLLMProvider()

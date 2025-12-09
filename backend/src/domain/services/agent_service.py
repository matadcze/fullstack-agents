from typing import List, NamedTuple, Protocol


class AgentStep(NamedTuple):
    step_type: str
    content: str


class LLMProvider(Protocol):
    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Generate a response from an LLM."""
        ...


class AgentService:
    """Thin agent orchestrator that delegates to an LLM provider."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def run(self, prompt: str, *, system: str | None = None) -> tuple[str, List[AgentStep]]:
        steps: List[AgentStep] = [
            AgentStep(step_type="thought", content="Parsing request and preparing the plan."),
        ]

        completion = await self.provider.generate(prompt, system=system)
        steps.append(AgentStep(step_type="response", content=completion))

        return completion, steps

from fastapi import APIRouter, Depends

from src.api.schemas import AgentRunRequest, AgentRunResponse, AgentStep
from src.domain.services import AgentService
from src.infrastructure.dependencies import get_agent_service

router = APIRouter(prefix="/agents", tags=["Agent"])


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    request: AgentRunRequest,
    agent_service: AgentService = Depends(get_agent_service),
):
    output, steps = await agent_service.run(request.prompt, system=request.system)
    return AgentRunResponse(
        output=output,
        steps=[AgentStep(step_type=s.step_type, content=s.content) for s in steps],
    )

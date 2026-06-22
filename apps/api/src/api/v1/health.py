from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import HealthResponse, ReadinessResponse
from src.core.config import settings
from src.infrastructure.database.session import get_db

router = APIRouter(tags=["Health & Monitoring"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy")


@router.get("/readiness", response_model=ReadinessResponse)
async def readiness_check(db: AsyncSession = Depends(get_db)):
    components = {}
    all_ready = True

    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar_one()
        components["database"] = "healthy"
    except Exception as e:
        components["database"] = f"unhealthy: {str(e)}"
        all_ready = False

    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        await redis_client.close()
        components["redis"] = "healthy"
    except Exception as e:
        components["redis"] = f"unhealthy: {str(e)}"
        all_ready = False

    try:
        if settings.upload_dir.exists():
            components["storage"] = "healthy"
        else:
            components["storage"] = "unhealthy: upload directory does not exist"
            all_ready = False
    except Exception as e:
        components["storage"] = f"unhealthy: {str(e)}"
        all_ready = False

    overall_status = "ready" if all_ready else "not_ready"

    if not all_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": overall_status,
                "components": components,
            },
        )

    return ReadinessResponse(status=overall_status, components=components)

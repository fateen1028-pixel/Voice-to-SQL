from fastapi import APIRouter
from api.routes.clarification import router as clarification_router
from api.routes.confirmation import router as confirmation_router
from api.routes.history import router as history_router
from api.routes.query import router as query_router
from api.routes.schema import router as schema_router
from api.routes.voice import router as voice_router

router = APIRouter()
router.include_router(query_router)
router.include_router(voice_router)
router.include_router(clarification_router)
router.include_router(confirmation_router)
router.include_router(schema_router)
router.include_router(history_router)

__all__ = ["router"]

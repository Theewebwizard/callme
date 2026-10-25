"""
Modular API routers aggregation.
"""

from fastapi import APIRouter

from backend.api.routers.businesses import router as businesses_router
from backend.api.routers.faqs import router as faqs_router
from backend.api.routers.tools import router as tools_router
from backend.api.routers.calls import router as calls_router
from backend.api.routers.playground import router as playground_router
from backend.api.routers.pending_actions import router as pending_actions_router
from backend.api.routers.voice import router as voice_router
from backend.api.routers.web_voice import router as web_voice_router
from backend.api.routers.admin import router as admin_router

api_router = APIRouter()

api_router.include_router(businesses_router)
api_router.include_router(faqs_router)
api_router.include_router(tools_router)
api_router.include_router(calls_router)
api_router.include_router(playground_router)
api_router.include_router(pending_actions_router)
api_router.include_router(voice_router)
api_router.include_router(voice_router, prefix="/v1")
api_router.include_router(web_voice_router)
api_router.include_router(admin_router)

__all__ = ["api_router"]

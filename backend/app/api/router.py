from fastapi import APIRouter, Depends

from app.core.rate_limit import enforce_api_limit
from app.modules.analysis.router import router as analysis_router
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.documents.router import router as documents_router

# Health probes are mounted outside this router, so the shared limit never refuses them.
api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(enforce_api_limit)])
api_router.include_router(auth_router)
api_router.include_router(documents_router)
api_router.include_router(chat_router)
api_router.include_router(analysis_router)

from fastapi import APIRouter
from modules.api.endpoints import tasks, analysis

api_router = APIRouter()

api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
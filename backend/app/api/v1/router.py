from fastapi import APIRouter
from app.api.v1.endpoints import repository, query, report, dashboard

api_router = APIRouter()

api_router.include_router(repository.router, prefix="/repositories", tags=["Repositories"])
api_router.include_router(query.router,      prefix="/query",        tags=["Query"])
api_router.include_router(report.router,     prefix="/reports",      tags=["Reports"])
api_router.include_router(dashboard.router,  prefix="/dashboard",    tags=["Dashboard"])

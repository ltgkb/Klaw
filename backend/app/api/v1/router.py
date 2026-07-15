"""v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent_flows,
    auth,
    health,
    kb,
    memories,
    notifications,
    providers,
    schedules,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(kb.router)
api_router.include_router(agent_flows.router)
api_router.include_router(providers.router)
api_router.include_router(memories.router)
api_router.include_router(schedules.router)
api_router.include_router(notifications.router)
api_router.include_router(health.router)

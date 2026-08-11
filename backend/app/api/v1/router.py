"""v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent_chat,
    agent_flows,
    auth,
    files,
    health,
    kb,
    kai_knowledge_api,
    local_agent,
    memories,
    notifications,
    providers,
    push_channels,
    public_chat,
    schedules,
    supplier_api,
    system_settings,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(kb.router)
api_router.include_router(agent_flows.router)
api_router.include_router(agent_chat.router)
api_router.include_router(public_chat.router)
api_router.include_router(supplier_api.router)
api_router.include_router(kai_knowledge_api.router)
api_router.include_router(providers.router)
api_router.include_router(memories.router)
api_router.include_router(schedules.router)
api_router.include_router(notifications.router)
api_router.include_router(push_channels.router)
api_router.include_router(local_agent.router)
api_router.include_router(files.router)
api_router.include_router(system_settings.router)
api_router.include_router(health.router)

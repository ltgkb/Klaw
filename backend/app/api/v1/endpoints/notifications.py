"""推送通知端点。对齐 PRD M4。"""

from fastapi import APIRouter

from app.core.deps import CurrentUser
from app.core.notify_client import notify
from app.schemas.notification import NotifyRequest, NotifyResponse, NotifyResult

router = APIRouter(prefix="/notifications", tags=["推送通知"])


@router.post("/send", response_model=NotifyResponse)
async def send_notification(data: NotifyRequest, current_user: CurrentUser):
    """立即推送消息到指定渠道。"""
    results = await notify(
        [ch.model_dump() for ch in data.channels],
        data.title,
        data.content,
    )
    return NotifyResponse(results=[NotifyResult(**r) for r in results])

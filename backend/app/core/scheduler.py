"""APScheduler 定时调度器。对齐 PRD 5.1 / M4。

JobStore = PostgreSQL (持久化, 重启后任务不丢失)。
调度回调: 创建 Execution → 调 execution_service.run_flow。
"""

import logging
import uuid
from datetime import datetime

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings

logger = logging.getLogger("claw.scheduler")

scheduler: AsyncIOScheduler | None = None


def init_scheduler():
    """初始化 APScheduler, JobStore=PostgreSQL。在应用启动时调用。"""
    global scheduler
    jobstore = SQLAlchemyJobStore(url=settings.sync_postgres_url)
    scheduler = AsyncIOScheduler(
        jobstores={"default": jobstore},
        timezone="Asia/Shanghai",
    )
    scheduler.start()
    logger.info("APScheduler 已启动 (PostgreSQL JobStore)")


def shutdown_scheduler():
    """关闭调度器。在应用关闭时调用。"""
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler 已关闭")


def schedule_flow(
    job_id: str,
    flow_id: uuid.UUID,
    cron: str,
    input_data: dict | None,
    name: str,
) -> datetime | None:
    """添加定时任务: 按 cron 表达式触发 flow 执行。

    Args:
        job_id: APScheduler job ID (用 ScheduleJob.id)
        flow_id: 工作流 UUID
        cron: cron 表达式 (如 "0 9 * * *" 每天 9 点)
        input_data: 执行输入
        name: 任务名称

    Returns:
        下次执行时间, 或 None
    """
    if scheduler is None:
        logger.error("调度器未初始化")
        return None

    trigger = validate_cron(cron)

    job = scheduler.add_job(
        _execute_scheduled_flow,
        trigger=trigger,
        id=job_id,
        name=name,
        kwargs={
            "flow_id": str(flow_id),
            "input_data": input_data or {},
            "job_id": job_id,
        },
        replace_existing=True,
    )
    logger.info("定时任务已添加: job_id=%s flow=%s cron=%s next_run=%s", job_id, flow_id, cron, job.next_run_time)
    return job.next_run_time


def validate_cron(cron: str) -> CronTrigger:
    """Validate a standard five-field cron expression."""
    if len(cron.split()) != 5:
        raise ValueError("cron 表达式必须包含 5 个字段")
    return CronTrigger.from_crontab(cron, timezone="Asia/Shanghai")


def unschedule_flow(job_id: str):
    """移除定时任务。"""
    if scheduler is None:
        return
    try:
        scheduler.remove_job(job_id)
        logger.info("定时任务已移除: %s", job_id)
    except Exception:
        pass  # job 不存在时忽略


def pause_scheduled_job(job_id: str):
    """暂停定时任务。"""
    if scheduler is None:
        return
    try:
        scheduler.pause_job(job_id)
        logger.info("定时任务已暂停: %s", job_id)
    except Exception:
        pass


def resume_scheduled_job(job_id: str) -> datetime | None:
    """恢复定时任务。返回下次执行时间。"""
    if scheduler is None:
        return None
    try:
        job = scheduler.resume_job(job_id)
        logger.info("定时任务已恢复: %s next_run=%s", job_id, job.next_run_time)
        return job.next_run_time
    except Exception:
        return None


def get_next_run_time(job_id: str) -> datetime | None:
    """获取任务的下次执行时间。"""
    if scheduler is None:
        return None
    try:
        job = scheduler.get_job(job_id)
        return job.next_run_time if job else None
    except Exception:
        return None


async def _execute_scheduled_flow(
    flow_id: str, input_data: dict, job_id: str | None = None
):
    """APScheduler 回调: 创建 Execution + 调 execution_service.run_flow。"""
    from app.core.database import async_session_factory
    from app.services import agent_flow_service, execution_service

    logger.info("定时触发: flow=%s", flow_id)
    try:
        async with async_session_factory() as db:
            execution = await agent_flow_service.create_execution(
                db, uuid.UUID(flow_id), input_data
            )
        await execution_service.run_flow(execution.id, uuid.UUID(flow_id))
    except Exception:
        logger.exception("定时任务执行失败: flow=%s", flow_id)
    finally:
        if job_id:
            try:
                from sqlalchemy import select

                from app.models.schedule_job import ScheduleJob

                async with async_session_factory() as db:
                    result = await db.execute(
                        select(ScheduleJob).where(ScheduleJob.id == uuid.UUID(job_id))
                    )
                    schedule_job = result.scalar_one_or_none()
                    if schedule_job is not None:
                        schedule_job.next_run_time = get_next_run_time(job_id)
                        await db.commit()
            except Exception:
                logger.exception("更新定时任务下次运行时间失败: job_id=%s", job_id)

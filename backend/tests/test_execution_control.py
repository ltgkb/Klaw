"""执行控制端点测试 (WP3)。

覆盖: pause/resume/cancel 端点、SSE 越权校验 (execution.flow_id)、
惰性 reaper (running/paused 超 30 分钟置 failed)、删除 flow 级联 unschedule (契约3)。
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import create_access_token
from app.models.execution import Execution, ExecutionStatus
from app.models.schedule_job import ScheduleJob


# ── 辅助函数 ──

async def _register_and_login(client, email="ctrl@test.com", password="secret123"):
    await client.post("/api/v1/auth/register", json={
        "email": email, "name": "Ctrl User", "password": password,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


async def _create_flow(client, token, name="CtrlFlow"):
    resp = await client.post("/api/v1/agent-flows", json={"name": name}, headers=_auth_headers(token))
    assert resp.status_code == 201
    return resp.json()["id"]


async def _insert_execution(db_session, flow_id, status=ExecutionStatus.running, node_states=None):
    ex = Execution(
        flow_id=uuid.UUID(flow_id) if isinstance(flow_id, str) else flow_id,
        status=status,
        input={"input": "x"},
        node_states=node_states,
    )
    db_session.add(ex)
    await db_session.commit()
    return ex


# ── 暂停 / 恢复 / 取消端点 ──

@pytest.mark.asyncio
async def test_pause_resume_cancel_running_execution(client, db_session):
    """running 执行可暂停→恢复→取消; 已取消后再次取消返回 400。"""
    token = await _register_and_login(client)
    flow_id = await _create_flow(client, token)
    ex = await _insert_execution(
        db_session,
        flow_id,
        ExecutionStatus.running,
        node_states={"slow": {"status": "running", "label": "Slow node"}},
    )

    resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/pause", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"

    resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/resume", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/cancel", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["error_message"] == "执行已取消"
    assert resp.json()["node_states"]["slow"]["status"] == "cancelled"
    assert resp.json()["node_states"]["slow"]["ended_at"]


@pytest.mark.asyncio
async def test_cancel_finished_execution_400(client, db_session):
    """已终态 (success/failed) 的执行不可取消。"""
    token = await _register_and_login(client, "ctrlfinished@test.com")
    flow_id = await _create_flow(client, token)
    ex = await _insert_execution(db_session, flow_id, ExecutionStatus.success)

    resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/cancel", headers=_auth_headers(token))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pause_pending_execution_400(client, db_session):
    """pending 状态不可暂停 (只有 running 可以)。"""
    token = await _register_and_login(client, "ctrlpending@test.com")
    flow_id = await _create_flow(client, token)
    ex = await _insert_execution(db_session, flow_id, ExecutionStatus.pending)

    resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/pause", headers=_auth_headers(token))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resume_not_paused_400(client, db_session):
    """未暂停的执行不可恢复。"""
    token = await _register_and_login(client, "ctrlresume@test.com")
    flow_id = await _create_flow(client, token)
    ex = await _insert_execution(db_session, flow_id, ExecutionStatus.running)

    resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/resume", headers=_auth_headers(token))
    assert resp.status_code == 400


# ── SSE 越权校验 (P1-1) ──

@pytest.mark.asyncio
async def test_sse_stream_wrong_flow_forbidden(client, db_session):
    """用己方 flow_id + 他人 execution_id 请求 SSE 返回 404 (不泄漏存在性); 不存在的 execution 同样 404。"""
    token_a = await _register_and_login(client, "sse_a@test.com")
    flow_a = await _create_flow(client, token_a, "FlowA")
    ex_a = await _insert_execution(
        db_session, flow_a, ExecutionStatus.success,
        node_states={"n1": {"status": "success", "output": "secret"}},
    )

    token_b = await _register_and_login(client, "sse_b@test.com")
    flow_b = await _create_flow(client, token_b, "FlowB")

    # B 用自己的 flow + A 的 execution → 404 (deploy 语义: 跨 flow/越权统一 404, 防信息泄漏)
    resp = await client.get(
        f"/api/v1/agent-flows/{flow_b}/executions/{ex_a.id}/stream",
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404

    # B 用自己的 flow + 不存在的 execution → 404
    resp = await client.get(
        f"/api/v1/agent-flows/{flow_b}/executions/{uuid.uuid4()}/stream",
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404

    # 无 token → 401
    resp = await client.get(f"/api/v1/agent-flows/{flow_b}/executions/{ex_a.id}/stream")
    assert resp.status_code == 401

    # URL query 中即使带有效 token 也不再接受，防止凭据进入访问日志。
    resp = await client.get(
        f"/api/v1/agent-flows/{flow_b}/executions/{uuid.uuid4()}/stream?token={token_b}"
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_stream_terminal_execution(client, db_session):
    """Bearer Header 认证后，终态执行的 SSE 立即推送 complete 事件并结束。"""
    token = await _register_and_login(client, "sse_ok@test.com")
    flow_id = await _create_flow(client, token)
    ex = await _insert_execution(
        db_session, flow_id, ExecutionStatus.success,
        node_states={"n1": {"status": "success", "output": "done"}},
    )

    resp = await client.get(
        f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/stream",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    assert "complete" in resp.text
    assert str(ex.id) in resp.text


@pytest.mark.asyncio
async def test_sse_observes_completion_committed_by_executor_session(
    client, db_session, db_engine, monkeypatch
):
    """流打开时为 pending，独立执行器 session 提交 success 后必须发 complete 并结束。"""
    token = await _register_and_login(client, "sse_live@test.com")
    flow_id = await _create_flow(client, token)
    ex = await _insert_execution(db_session, flow_id, ExecutionStatus.pending)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    real_sleep = asyncio.sleep

    async def fast_sleep(_seconds):
        await real_sleep(0.01)

    monkeypatch.setattr("app.api.v1.endpoints.agent_flows.asyncio.sleep", fast_sleep)

    async def complete_from_executor_session():
        await real_sleep(0.05)
        async with factory() as executor_db:
            await executor_db.execute(
                update(Execution)
                .where(Execution.id == ex.id)
                .values(
                    status=ExecutionStatus.success,
                    node_states={"n1": {"status": "success", "output": "done"}},
                )
            )
            await executor_db.commit()

    task = asyncio.create_task(complete_from_executor_session())
    resp = await asyncio.wait_for(
        client.get(
            f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/stream",
            headers=_auth_headers(token),
        ),
        timeout=1,
    )
    await task

    assert resp.status_code == 200
    assert "event: complete" in resp.text
    assert '"status": "success"' in resp.text


@pytest.mark.asyncio
async def test_sse_header_ignores_query_token(client, db_session):
    """Header 凭据是唯一认证来源，URL 中的伪造 token 不影响安全 Header。"""
    token = await _register_and_login(client, "sse_header@test.com")
    flow_id = await _create_flow(client, token)
    ex = await _insert_execution(db_session, flow_id, ExecutionStatus.success)

    resp = await client.get(
        f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/stream?token=invalid",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    assert "complete" in resp.text


@pytest.mark.asyncio
async def test_sse_rejects_disabled_user_and_malformed_subject(client, db_session):
    """SSE 与普通 API 一致拦截禁用用户，并把畸形 JWT subject 作为 401。"""
    token = await _register_and_login(client, "sse_disabled@test.com")
    flow_id = await _create_flow(client, token)
    ex = await _insert_execution(db_session, flow_id, ExecutionStatus.success)

    from app.models.user import User

    user = (await db_session.execute(select(User).where(User.email == "sse_disabled@test.com"))).scalar_one()
    user.is_active = False
    await db_session.commit()

    url = f"/api/v1/agent-flows/{flow_id}/executions/{ex.id}/stream"
    resp = await client.get(url, headers=_auth_headers(token))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "用户已被禁用"

    malformed = create_access_token("not-a-uuid")
    resp = await client.get(url, headers=_auth_headers(malformed))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "无效令牌"


# ── 惰性 reaper (P1-2) ──

@pytest.mark.asyncio
async def test_reaper_on_list_executions(client, db_session):
    """list 执行时, running 且 updated_at 超 30 分钟的记录被置 failed「服务重启中断」。"""
    token = await _register_and_login(client, "reaper_list@test.com")
    flow_id = await _create_flow(client, token)
    stale = await _insert_execution(db_session, flow_id, ExecutionStatus.running)
    fresh = await _insert_execution(db_session, flow_id, ExecutionStatus.running)

    await db_session.execute(
        update(Execution)
        .where(Execution.id == stale.id)
        .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=40))
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/agent-flows/{flow_id}/executions", headers=_auth_headers(token))
    assert resp.status_code == 200
    by_id = {item["id"]: item for item in resp.json()}
    assert by_id[str(stale.id)]["status"] == "failed"
    assert by_id[str(stale.id)]["error_message"] == "服务重启中断"
    assert by_id[str(fresh.id)]["status"] == "running"  # 未超时的不受影响


@pytest.mark.asyncio
async def test_reaper_on_get_execution(client, db_session):
    """get 执行详情时同样触发惰性回收 (paused 超时也回收)。"""
    token = await _register_and_login(client, "reaper_get@test.com")
    flow_id = await _create_flow(client, token)
    stale = await _insert_execution(db_session, flow_id, ExecutionStatus.paused)

    await db_session.execute(
        update(Execution)
        .where(Execution.id == stale.id)
        .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=45))
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/agent-flows/{flow_id}/executions/{stale.id}", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert resp.json()["error_message"] == "服务重启中断"


# ── 契约3: 删除 flow 级联 unschedule ──

@pytest.mark.asyncio
async def test_delete_flow_unschedules_jobs(client, db_session, monkeypatch):
    """删除工作流时, 其关联 ScheduleJob 逐个调用 scheduler.unschedule_flow。"""
    token = await _register_and_login(client, "cascade@test.com")
    flow_id = await _create_flow(client, token)

    job = ScheduleJob(flow_id=uuid.UUID(flow_id), name="每日任务", cron="0 9 * * *")
    db_session.add(job)
    await db_session.commit()

    calls = []
    monkeypatch.setattr(
        "app.core.scheduler.unschedule_flow", lambda job_id: calls.append(job_id)
    )

    resp = await client.delete(f"/api/v1/agent-flows/{flow_id}", headers=_auth_headers(token))
    assert resp.status_code == 204
    assert calls == [str(job.id)]

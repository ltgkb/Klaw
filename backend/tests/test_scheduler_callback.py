"""定时任务修复验证测试 (WP5)。

覆盖: 非法 cron 422 且无孤儿行、改 input 触发重注册、paused 改 cron 恢复用新 cron、
调度回调创建 Execution (mock run_flow)、调度器不可用 503、schedule_flow 严格校验。
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


# ── 辅助函数 (沿用 test_m4.py 模式) ──

async def _register_and_login(client, email="schedfix@test.com", password="secret123"):
    await client.post("/api/v1/auth/register", json={
        "email": email, "name": "Sched Fix User", "password": password,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


async def _create_flow(client, headers, name="定时修复测试流程"):
    resp = await client.post("/api/v1/agent-flows", json={"name": name}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
def mock_scheduler(monkeypatch):
    """Mock APScheduler 并记录调用参数。"""
    from app.core import scheduler as sched_module

    calls = {"schedule_flow": [], "unschedule": [], "pause": []}

    def mock_schedule_flow(job_id, flow_id, cron, input_data, name):
        calls["schedule_flow"].append({
            "job_id": job_id, "flow_id": flow_id,
            "cron": cron, "input_data": input_data, "name": name,
        })
        return datetime.now(timezone.utc)

    def mock_unschedule_flow(job_id):
        calls["unschedule"].append(job_id)

    def mock_pause(job_id):
        calls["pause"].append(job_id)
        return True

    monkeypatch.setattr(sched_module, "schedule_flow", mock_schedule_flow)
    monkeypatch.setattr(sched_module, "unschedule_flow", mock_unschedule_flow)
    monkeypatch.setattr(sched_module, "pause_scheduled_job", mock_pause)
    return calls


# ── Cron P1-1: 非法 cron → 422, 且不产生孤儿行 ──

@pytest.mark.asyncio
async def test_invalid_cron_422_no_orphan_row(client, mock_scheduler):
    """非法 cron 表达式 → 422, DB 中不留孤儿行。"""
    token = await _register_and_login(client)
    h = _auth_headers(token)
    flow_id = await _create_flow(client, h)

    for bad_cron in ("not-a-cron", "0 9 * *", "0 9 * * * *", "61 * * * *"):
        resp = await client.post("/api/v1/schedules", json={
            "flow_id": flow_id, "name": "坏任务", "cron": bad_cron,
        }, headers=h)
        assert resp.status_code == 422, f"cron={bad_cron!r} 应返回 422"

    # 无孤儿行, 也未注册任何 APScheduler job
    resp = await client.get("/api/v1/schedules", headers=h)
    assert resp.status_code == 200
    assert resp.json() == []
    assert mock_scheduler["schedule_flow"] == []


@pytest.mark.asyncio
async def test_update_invalid_cron_422(client, mock_scheduler):
    """更新为非法 cron → 422。"""
    token = await _register_and_login(client, "badcron2@test.com")
    h = _auth_headers(token)
    flow_id = await _create_flow(client, h)

    resp = await client.post("/api/v1/schedules", json={
        "flow_id": flow_id, "name": "正常任务", "cron": "0 9 * * *",
    }, headers=h)
    sched_id = resp.json()["id"]

    resp = await client.put(f"/api/v1/schedules/{sched_id}", json={
        "cron": "99 25 * * *",
    }, headers=h)
    assert resp.status_code == 422


# ── Cron P1-1/P2-7: 调度器不可用 → 503 且回滚已建行 ──

@pytest.mark.asyncio
async def test_create_schedule_scheduler_unavailable_503(client, monkeypatch):
    """schedule_flow 返回 None (调度器不可用) → 503, 已建行回滚。"""
    from app.core import scheduler as sched_module

    monkeypatch.setattr(sched_module, "schedule_flow", lambda **kwargs: None)

    token = await _register_and_login(client, "unavail@test.com")
    h = _auth_headers(token)
    flow_id = await _create_flow(client, h)

    resp = await client.post("/api/v1/schedules", json={
        "flow_id": flow_id, "name": "无调度器任务", "cron": "0 9 * * *",
    }, headers=h)
    assert resp.status_code == 503

    resp = await client.get("/api/v1/schedules", headers=h)
    assert resp.json() == []


@pytest.mark.asyncio
async def test_pause_failure_returns_503_without_committing_paused_state(
    client, mock_scheduler, monkeypatch
):
    from app.core import scheduler as sched_module

    token = await _register_and_login(client, "pausefail@test.com")
    headers = _auth_headers(token)
    flow_id = await _create_flow(client, headers)
    created = await client.post(
        "/api/v1/schedules",
        json={"flow_id": flow_id, "name": "Pause failure", "cron": "0 9 * * *"},
        headers=headers,
    )
    schedule_id = created.json()["id"]
    monkeypatch.setattr(sched_module, "pause_scheduled_job", lambda _job_id: False)

    response = await client.put(
        f"/api/v1/schedules/{schedule_id}",
        json={"status": "paused"},
        headers=headers,
    )

    assert response.status_code == 503
    current = await client.get(f"/api/v1/schedules/{schedule_id}", headers=headers)
    assert current.json()["status"] == "active"


# ── Cron P1-2: 改 input 生效 (触发重注册) ──

@pytest.mark.asyncio
async def test_update_input_reregisters_job(client, mock_scheduler):
    """只改 input 也应重新注册 APScheduler job。"""
    token = await _register_and_login(client, "inputchg@test.com")
    h = _auth_headers(token)
    flow_id = await _create_flow(client, h)

    resp = await client.post("/api/v1/schedules", json={
        "flow_id": flow_id, "name": "改输入任务",
        "cron": "0 9 * * *", "input": {"k": "v1"},
    }, headers=h)
    sched_id = resp.json()["id"]
    assert len(mock_scheduler["schedule_flow"]) == 1

    resp = await client.put(f"/api/v1/schedules/{sched_id}", json={
        "input": {"k": "v2"},
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["input"] == {"k": "v2"}

    # 重注册了一次, 且带上新 input
    assert len(mock_scheduler["schedule_flow"]) == 2
    assert mock_scheduler["schedule_flow"][-1]["input_data"] == {"k": "v2"}


# ── Cron P1-3: paused 改 cron, 恢复时用新 cron 重建 job ──

@pytest.mark.asyncio
async def test_resume_rebuilds_with_new_cron(client, mock_scheduler):
    """paused 状态改 cron 不注册; 恢复时用新 cron 重建。"""
    token = await _register_and_login(client, "resume@test.com")
    h = _auth_headers(token)
    flow_id = await _create_flow(client, h)

    resp = await client.post("/api/v1/schedules", json={
        "flow_id": flow_id, "name": "恢复测试任务", "cron": "0 9 * * *",
    }, headers=h)
    sched_id = resp.json()["id"]
    assert len(mock_scheduler["schedule_flow"]) == 1

    # 暂停
    resp = await client.put(f"/api/v1/schedules/{sched_id}", json={
        "status": "paused",
    }, headers=h)
    assert resp.status_code == 200
    assert mock_scheduler["pause"] == [sched_id]

    # paused 状态改 cron → 不重注册
    resp = await client.put(f"/api/v1/schedules/{sched_id}", json={
        "cron": "30 8 * * *",
    }, headers=h)
    assert resp.status_code == 200
    assert len(mock_scheduler["schedule_flow"]) == 1

    # 恢复 → 用新 cron 重建 (走 schedule_flow 而非 resume_scheduled_job)
    resp = await client.put(f"/api/v1/schedules/{sched_id}", json={
        "status": "active",
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert len(mock_scheduler["schedule_flow"]) == 2
    assert mock_scheduler["schedule_flow"][-1]["cron"] == "30 8 * * *"


# ── 回调测试: _execute_scheduled_flow 创建 Execution 并调 run_flow (mock) ──

@pytest.mark.asyncio
async def test_scheduler_callback_creates_execution(db_engine, monkeypatch):
    """APScheduler 回调: 创建 Execution → 调 execution_service.run_flow。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.core.database as db_module
    from app.core import scheduler as sched_module
    from app.services import agent_flow_service, execution_service

    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)

    created = {}
    ran = {}

    async def mock_create_execution(db, flow_id, input_data=None):
        created["flow_id"] = flow_id
        created["input"] = input_data
        return SimpleNamespace(id=uuid.uuid4())

    async def mock_run_flow(execution_id, flow_id):
        ran["execution_id"] = execution_id
        ran["flow_id"] = flow_id

    monkeypatch.setattr(agent_flow_service, "create_execution", mock_create_execution)
    monkeypatch.setattr(execution_service, "run_flow", mock_run_flow)

    flow_id = uuid.uuid4()
    await sched_module._execute_scheduled_flow(str(flow_id), {"k": "v"})

    assert created["flow_id"] == flow_id
    assert created["input"] == {"k": "v"}
    assert ran["flow_id"] == flow_id
    assert ran["execution_id"] is not None


@pytest.mark.asyncio
async def test_scheduler_callback_failure_logged(db_engine, monkeypatch):
    """回调内部异常被捕获并记录, 不向外抛。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.core.database as db_module
    from app.core import scheduler as sched_module
    from app.services import agent_flow_service

    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)

    async def mock_create_execution_fail(db, flow_id, input_data=None):
        raise RuntimeError("DB 故障")

    monkeypatch.setattr(agent_flow_service, "create_execution", mock_create_execution_fail)

    # 不应抛出异常
    await sched_module._execute_scheduled_flow(str(uuid.uuid4()), {})


# ── schedule_flow 单元测试: 严格校验 cron (fake scheduler) ──

class _FakeJob:
    def __init__(self):
        self.next_run_time = datetime.now(timezone.utc)


class _FakeScheduler:
    def __init__(self):
        self.added = []

    def add_job(self, func, trigger, **kwargs):
        self.added.append({"func": func, "trigger": trigger, **kwargs})
        return _FakeJob()


def test_schedule_flow_rejects_invalid_cron(monkeypatch):
    """schedule_flow 对非法 cron 抛 ValueError (段数不对/字段越界)。"""
    from app.core import scheduler as sched_module

    monkeypatch.setattr(sched_module, "scheduler", _FakeScheduler())
    flow_id = uuid.uuid4()

    with pytest.raises(ValueError):
        sched_module.schedule_flow("j1", flow_id, "0 9 * * * *", None, "t")  # 6 段
    with pytest.raises(ValueError):
        sched_module.schedule_flow("j2", flow_id, "0 9 * *", None, "t")  # 4 段
    with pytest.raises(ValueError):
        sched_module.schedule_flow("j3", flow_id, "61 * * * *", None, "t")  # 分钟越界


def test_schedule_flow_registers_valid_cron(monkeypatch):
    """schedule_flow 合法 cron 注册成功并返回 next_run_time。"""
    from app.core import scheduler as sched_module

    fake = _FakeScheduler()
    monkeypatch.setattr(sched_module, "scheduler", fake)
    flow_id = uuid.uuid4()

    next_run = sched_module.schedule_flow("j1", flow_id, "0 9 * * *", {"a": 1}, "任务A")

    assert next_run is not None
    assert len(fake.added) == 1
    added = fake.added[0]
    assert added["id"] == "j1"
    assert added["name"] == "任务A"
    assert added["kwargs"] == {"flow_id": str(flow_id), "input_data": {"a": 1}, "job_id": "j1"}
    assert added["replace_existing"] is True


def test_schedule_flow_unschedule_signature_kept():
    """契约3: unschedule_flow(job_id) 签名保持不变。"""
    import inspect

    from app.core import scheduler as sched_module

    params = list(inspect.signature(sched_module.unschedule_flow).parameters)
    assert params == ["job_id"]

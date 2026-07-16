# -*- coding: utf-8 -*-
"""Сквозной смоук-тест E2-бэкенда (T-37): REST + Интерфейсный агент замыкают
контур подтверждения корректировки человеком через настоящий HTTP-слой, а не
агента-заглушку из прошлых тестов (analyst_adapter_smoke_test.py).

Путь целиком: AnalystAdapterAgent (propose-режим) шлёт FIPA propose
Интерфейсному агенту -> тот кладёт предложение в pending_decisions -> REST
GET /corrections/pending реально его видит (через FastAPI TestClient, тот
же api/main.py, что и в проде) -> REST POST /corrections/{id}/decide accept
-> Интерфейсный агент на следующем тике реально шлёт accept-proposal
Аналитик-Адаптеру -> тот применяет корректировку.

process_cycle() блокируется до ответа (или decision_timeout) — поэтому
запускается как параллельная asyncio-задача, а REST-шаги выполняются, пока
она ждёт.

Запуск: python -m agents.interface_flow_smoke_test
"""
from __future__ import annotations

import asyncio
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .xmpp_dev import enable_unencrypted_plain_auth

enable_unencrypted_plain_auth()

import spade  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.config import settings  # noqa: E402
from api.main import app  # noqa: E402
from mining.control_points import EXPERIMENT_CONTROL_POINTS  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402
from simgen.executor import ExecutorProfile  # noqa: E402
from simgen.run import run_cycle  # noqa: E402

from .analyst_adapter_agent import AnalystAdapterAgent  # noqa: E402
from .interface_agent import InterfaceAgent  # noqa: E402

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "experiment_process.bpmn"
RUN_ID = uuid.uuid4().hex[:6]
PASSWORD = "smoke-password"


def _auth_header(client: TestClient, username: str) -> dict:
    resp = client.post("/auth/token", data={"username": username, "password": username})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _wait_until(predicate, timeout: float = 10.0, interval: float = 0.3) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


async def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    process_key = f"e2_flow_{RUN_ID}"
    orch = Orchestrator(settings.database_url)
    run_cycle(
        orch, random.Random(11), ExecutorProfile(no_show_probability=0.5), process_key, BPMN, "experiment_process",
        n_instances=20, cycle_start=datetime(2026, 10, 1, tzinfo=timezone.utc), max_days=30,
        initial_data={"reminder_days": 7, "escalation_days": 14},
    )

    interface_jid = f"smoke-iface-{RUN_ID}@localhost"
    interface = InterfaceAgent(interface_jid, PASSWORD, settings.database_url, tick_seconds=0.5)
    await interface.start(auto_register=True)

    adapter_jid = f"smoke-adapter-iface-{RUN_ID}@localhost"
    adapter = AnalystAdapterAgent(
        adapter_jid, PASSWORD, settings.database_url,
        recipient_jid=interface_jid, decision_timeout=15.0,
    )
    await adapter.start(auto_register=True)

    cycle_task = asyncio.create_task(
        adapter.process_cycle(process_key, BPMN, EXPERIMENT_CONTROL_POINTS, mode="propose")
    )

    got_it = await _wait_until(lambda: len(interface.received) > 0, timeout=10)
    check("Интерфейсный агент реально получил FIPA propose", got_it)

    client = TestClient(app)
    headers = _auth_header(client, "dept_head")

    resp = client.get("/corrections/pending", headers=headers)
    check("REST-эндпоинт GET /corrections/pending отвечает 200", resp.status_code == 200)
    pending = [p for p in resp.json()["pending"] if p["process_key"] == process_key]
    check("REST реально видит предложение из БД (не заглушка)", len(pending) >= 1)

    if pending:
        decision_id = pending[0]["id"]
        decide_resp = client.post(
            f"/corrections/{decision_id}/decide", json={"decision": "accept"}, headers=headers,
        )
        check("REST POST /corrections/{id}/decide -> 200", decide_resp.status_code == 200)

        # повторное решение того же предложения — конфликт, не тихий успех
        repeat_resp = client.post(
            f"/corrections/{decision_id}/decide", json={"decision": "reject"}, headers=headers,
        )
        check("повторное решение уже решённого предложения -> 409, а не тихая перезапись",
              repeat_resp.status_code == 409)
    else:
        check("REST POST /corrections/{id}/decide -> 200", False)
        check("повторное решение уже решённого предложения -> 409, а не тихая перезапись", False)

    dispatched = await _wait_until(lambda: len(interface.dispatched) > 0, timeout=10)
    check("Интерфейсный агент реально отправил accept-proposal Аналитик-Адаптеру", dispatched)

    result = await asyncio.wait_for(cycle_task, timeout=20)
    check("Аналитик-Адаптер реально применил корректировку, решённую через REST",
          len(result.accepted) > 0 and result.version is not None)

    # доступ без токена и не той ролью — не должен пройти (ФТ-А-И-3)
    no_auth_resp = client.get("/corrections/pending")
    check("без токена -> 401", no_auth_resp.status_code == 401)

    supervisor_headers = _auth_header(client, "supervisor")  # роль есть, но не dept_head/admin
    wrong_role_resp = client.get("/corrections/pending", headers=supervisor_headers)
    check("роль 'supervisor' (не dept_head/admin) отклонена реальным запросом -> 403 (ФТ-А-И-3)",
          wrong_role_resp.status_code == 403)

    # --- Кабинет задач (T-37): /tasks, отдельно от корректировок ---
    task_case_id = f"e2_task_{RUN_ID}"
    orch.start_instance(
        task_case_id, f"e2_task_{RUN_ID}_process", BPMN, "experiment_process",
        initial_data={"reminder_days": 7, "escalation_days": 14},
    )

    tasks_resp = client.get("/tasks", headers=headers)
    check("REST GET /tasks -> 200", tasks_resp.status_code == 200)
    our_tasks = [t for t in tasks_resp.json()["tasks"] if t["case_id"] == task_case_id]
    check("REST реально видит READY-задачу свежего экземпляра", len(our_tasks) == 1)

    if our_tasks:
        complete_resp = client.post(
            f"/tasks/{task_case_id}/{our_tasks[0]['task_name']}/complete", json={}, headers=headers,
        )
        check("REST POST /tasks/.../complete -> 200", complete_resp.status_code == 200)
        state_after = orch.get_state(task_case_id)
        check("задача реально помечена выполненной в оркестраторе (не только в ответе REST)",
              all(t["state"] != "READY" for t in state_after["tasks"] if t["name"] == our_tasks[0]["task_name"]))
    else:
        check("REST POST /tasks/.../complete -> 200", False)
        check("задача реально помечена выполненной в оркестраторе (не только в ответе REST)", False)

    missing_resp = client.post(f"/tasks/no-such-case/some_task/complete", json={}, headers=headers)
    check("завершение задачи несуществующего экземпляра -> 404, а не тихий успех", missing_resp.status_code == 404)

    await adapter.stop()
    await interface.stop()

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(spade.run(main()))

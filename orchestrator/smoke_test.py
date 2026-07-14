# -*- coding: utf-8 -*-
"""Сквозной смоук-тест оркестратора (B1/T-31) на реальной PostgreSQL.

Запуск (нужен поднятый docker compose):  python -m orchestrator.smoke_test
Проверяет полный жизненный цикл экземпляра, включая две имитации рестарта
процесса Python между шагами (сериализация должна пережить это без потерь —
см. spikes/serialization_spike/FINDINGS.md).
"""
import sys
import time
import uuid
from pathlib import Path

from api.config import settings
import psycopg

from .engine import InstanceNotFound, Orchestrator, TaskNotReady

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "demo_process.bpmn"


def _events_for(case_id: str) -> list[tuple[str, str]]:
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute(
            "SELECT activity, lifecycle FROM event_log WHERE case_id=%s ORDER BY event_id", (case_id,)
        ).fetchall()


def main() -> int:
    case_id = f"demo-{uuid.uuid4().hex[:8]}"
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    print(f"case_id = {case_id}\n")

    orch = Orchestrator(settings.database_url)
    orch.start_instance(case_id, "demo_process", BPMN, "demo_process")
    state = orch.get_state(case_id)
    check("auto_step выполнен", any(t["name"] == "auto_step" and t["state"] == "COMPLETED" for t in state["tasks"]))
    check("review_request READY", any(t["name"] == "review_request" and t["state"] == "READY" for t in state["tasks"]))
    check("event_log: событие старта записано", ("process_instance", "start") in _events_for(case_id))

    del orch  # имитация рестарта процесса Python
    time.sleep(2.5)
    orch2 = Orchestrator(settings.database_url)
    orch2.tick(case_id)
    state2 = orch2.get_state(case_id)
    check("таймер напоминания сработал после рестарта", any(
        t["name"] == "remind" and t["state"] == "COMPLETED" for t in state2["tasks"]))
    check("review_request всё ещё READY", not state2["completed"])

    try:
        orch2.complete_task(case_id, "no_such_task")
        check("TaskNotReady для несуществующей задачи", False)
    except TaskNotReady:
        check("TaskNotReady для несуществующей задачи", True)

    orch2.complete_task(case_id, "review_request", data={"decision": "approved"}, resource="dept_head")
    del orch2
    orch3 = Orchestrator(settings.database_url)
    final = orch3.get_state(case_id)
    check("процесс завершён", final["completed"])
    check("event_log: событие завершения записано", ("process_instance", "complete") in _events_for(case_id))

    try:
        orch3.get_state("no-such-case")
        check("InstanceNotFound для чужого case_id", False)
    except InstanceNotFound:
        check("InstanceNotFound для чужого case_id", True)

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

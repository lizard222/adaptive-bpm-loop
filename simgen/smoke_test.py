# -*- coding: utf-8 -*-
"""Смоук-тест генератора (B5/T-35): воспроизводимость по seed (ФТ-С-9.2) и
работоспособность на реальной PostgreSQL.

Запуск: python -m simgen.smoke_test
"""
from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from api.config import settings
from orchestrator import Orchestrator

from .executor import ExecutorProfile
from .run import run_cycle

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "demo_process_days.bpmn"
RUN_ID = uuid.uuid4().hex[:6]
CYCLE_START = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _run(process_key: str, seed: int, n: int = 15, max_days: int = 30):
    orch = Orchestrator(settings.database_url)
    rng = random.Random(seed)
    executor = ExecutorProfile(no_show_probability=0.2)
    return run_cycle(orch, rng, executor, process_key, BPMN, "demo_process_days", n, CYCLE_START, max_days)


def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    key_a1 = f"demo_process_days_{RUN_ID}_a1"
    key_a2 = f"demo_process_days_{RUN_ID}_a2"
    key_b = f"demo_process_days_{RUN_ID}_b"

    report_a1 = _run(key_a1, seed=42)
    report_a2 = _run(key_a2, seed=42)
    report_b = _run(key_b, seed=777)

    print(report_a1)
    print(report_a2)
    print(report_b)

    check("все экземпляры первого прогона обработаны (завершены или ещё активны)",
          report_a1.completed + report_a1.still_active == report_a1.started == 15)
    check("есть хотя бы одно напоминание за цикл (правдоподобность симуляции)", report_a1.reminders > 0)

    same_seed_fields = (
        report_a1.completed, report_a1.still_active, report_a1.reminders,
        report_a1.escalations, report_a1.mean_duration_days,
    )
    other_seed_fields = (
        report_a2.completed, report_a2.still_active, report_a2.reminders,
        report_a2.escalations, report_a2.mean_duration_days,
    )
    check("одинаковый seed -> идентичный отчёт (детерминизм, ФТ-С-9.2)",
          same_seed_fields == other_seed_fields)

    diff_seed_fields = (
        report_b.completed, report_b.still_active, report_b.reminders,
        report_b.escalations, report_b.mean_duration_days,
    )
    check("другой seed -> отчёт отличается (не константа, реально использует rng)",
          diff_seed_fields != same_seed_fields)

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

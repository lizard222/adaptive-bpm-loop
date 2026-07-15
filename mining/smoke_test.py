# -*- coding: utf-8 -*-
"""Смоук-тест конвейера анализа (C1/T-40) на данных из генератора (simgen, T-35).

Запуск: python -m mining.smoke_test
"""
from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from api.config import settings
from orchestrator import Orchestrator
from simgen.executor import ExecutorProfile
from simgen.run import run_cycle

from .control_points import DEMO_CONTROL_POINTS
from .conveyor import analyze_cycle

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "demo_process_days.bpmn"
RUN_ID = uuid.uuid4().hex[:6]


def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    process_key = f"demo_process_days_{RUN_ID}"
    orch = Orchestrator(settings.database_url)
    rng = random.Random(123)
    executor = ExecutorProfile(no_show_probability=0.3)  # заметная доля просрочек для теста
    sim_report = run_cycle(
        orch, rng, executor, process_key, BPMN, "demo_process_days",
        n_instances=25, cycle_start=datetime(2026, 10, 1, tzinfo=timezone.utc), max_days=30,
    )
    print(sim_report)

    report = analyze_cycle(settings.database_url, process_key, BPMN, DEMO_CONTROL_POINTS)
    print(report)

    cp = report.control_points["review_request"]
    check("конвейер увидел все экземпляры цикла", report.n_cases == sim_report.started)
    check("вовремя + с напоминанием + с эскалацией = все экземпляры",
          cp.on_time + cp.reminded + cp.escalated == report.n_cases)
    check("число случаев с эскалацией совпадает с генератором", cp.escalated == sim_report.escalations)
    check("fitness посчитан и лежит в [0, 1]", report.fitness is not None and 0.0 <= report.fitness <= 1.0)
    check("precision посчитан и лежит в [0, 1]", report.precision is not None and 0.0 <= report.precision <= 1.0)
    # Не ~1.0: pm4py конвертирует граничные события BPMN в сеть Петри не
    # вполне точно (remind/escalate оказываются не привязаны причинно к
    # review_request) — экземпляры с эскалацией получают fitness=0.667
    # детерминированно, "на ровном месте" экземпляры без эскалации — 1.000.
    # Известный предел инструмента, не ошибка модели/журнала.
    # Подробности — mining/conveyor.py (docstring _load_normative_petri_net).
    check("замкнутая синтетическая система структурно конформна (fitness > 0.8)",
          report.fitness is not None and report.fitness > 0.8)

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Смоук-тест алгоритма корректировок (C2/T-41).

Две части:
  1. Сквозная, на реальном пайплайне simgen -> conveyor -> corrections:
     процесс с высокой долей no-show должен получить корректировку
     shift_start; процесс, где почти все укладываются в срок — не получить
     ничего (нет ложных срабатываний при нормальном поведении процесса).
  2. Модульная, на искусственно собранном ConveyorReport: проверяет ветку
     add_checkpoint (систематический пропуск) и защиту от маленькой выборки
     — без обращения к БД, эти сценарии пока не воспроизводятся органически
     через текущую демо-модель (см. mining/conveyor.py, известное
     ограничение конвертации граничных событий в pm4py).

Запуск: python -m mining.corrections_smoke_test
"""
from __future__ import annotations

import random
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from api.config import settings
from orchestrator import Orchestrator
from simgen.executor import ExecutorProfile
from simgen.run import run_cycle

from .control_points import DEMO_CONTROL_POINTS
from .conveyor import ConveyorReport, ControlPointStats, analyze_cycle
from .corrections import Thresholds, propose_corrections

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "demo_process_days.bpmn"
RUN_ID = uuid.uuid4().hex[:6]


def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    orch = Orchestrator(settings.database_url)

    # --- Часть 1: сквозной пайплайн ---
    key_bad = f"demo_process_days_{RUN_ID}_bad"
    rng_bad = random.Random(1)
    sim_bad = run_cycle(
        orch, rng_bad, ExecutorProfile(no_show_probability=0.5), key_bad, BPMN, "demo_process_days",
        n_instances=20, cycle_start=datetime(2026, 10, 1, tzinfo=timezone.utc), max_days=30,
    )
    report_bad = analyze_cycle(settings.database_url, key_bad, BPMN, DEMO_CONTROL_POINTS)
    corrections_bad = propose_corrections(report_bad)
    print(sim_bad)
    print(report_bad)
    for c in corrections_bad:
        print(" ", c)

    check("процесс с высокой долей no-show получил корректировку shift_start",
          any(c.kind == "shift_start" and c.target == "review_request" for c in corrections_bad))

    key_good = f"demo_process_days_{RUN_ID}_good"
    rng_good = random.Random(2)
    sim_good = run_cycle(
        orch, rng_good, ExecutorProfile(no_show_probability=0.0, delay_median_days=1.0), key_good, BPMN,
        "demo_process_days", n_instances=20, cycle_start=datetime(2026, 10, 1, tzinfo=timezone.utc), max_days=30,
    )
    report_good = analyze_cycle(settings.database_url, key_good, BPMN, DEMO_CONTROL_POINTS)
    corrections_good = propose_corrections(report_good)
    print(sim_good)
    print(report_good)

    check("процесс, укладывающийся в срок, не получил ни одной корректировки (нет ложных срабатываний)",
          len(corrections_good) == 0)

    # --- Часть 2: модульная проверка на искусственном отчёте ---
    crafted = ConveyorReport(
        process_key="crafted",
        n_cases=20,
        fitness=1.0,
        precision=1.0,
        skipped_activities=Counter({"nomocontrol_check": 6}),  # 30% > порога 20%
        control_points={
            "review_request": ControlPointStats(task="review_request", n_cases=20, on_time=20, reminded=0, escalated=0),
        },
    )
    crafted_corrections = propose_corrections(crafted)
    check("систематический пропуск шага -> корректировка add_checkpoint",
          any(c.kind == "add_checkpoint" and c.target == "nomocontrol_check" for c in crafted_corrections))
    check("нет ложного shift_start для контрольной точки без просрочек",
          not any(c.kind in ("shift_start", "review_duration") for c in crafted_corrections))

    tiny_sample = ConveyorReport(
        process_key="tiny", n_cases=2, fitness=1.0, precision=1.0,
        skipped_activities=Counter({"x": 2}),
        control_points={"x": ControlPointStats(task="x", n_cases=2, on_time=0, reminded=0, escalated=2)},
    )
    check("защита от маленькой выборки: корректировки не предлагаются (min_sample_size)",
          propose_corrections(tiny_sample, Thresholds(min_sample_size=5)) == [])

    check("вручную заданный порог влияет на результат (конфигурируемость метода)",
          len(propose_corrections(crafted, Thresholds(skip_fraction=0.5))) == 0)

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

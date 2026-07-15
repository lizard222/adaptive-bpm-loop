# -*- coding: utf-8 -*-
"""Эксперимент: базовый режим vs адаптивный (D1-D3, T-50/T-51).

Дизайн (T-50):
  - Модель: bpmn/demo/experiment_process.bpmn, одна контрольная точка
    (review_request), параметризованные таймеры reminder_days/escalation_days
    (spikes/param_timer_spike/FINDINGS.md) — контур адаптации меняет их между
    циклами, не переписывая BPMN-файл.
  - Два режима на каждый seed:
      * baseline — параметры процесса ФИКСИРОВАНЫ на всех циклах; контур
        адаптации анализирует каждый цикл (для сравнения — «что было бы
        предложено»), но НИКОГДА не применяет корректировки;
      * adaptive — контур включён в режиме "auto" (ФТ-С-7.6): принятые
        корректировки меняют параметры СЛЕДУЮЩЕГО цикла
        (mining/corrections.py -> experiment/params.py).
  - Честность сравнения: оба режима на одном (seed, cycle) используют
    ОДИНАКОВЫЙ подсев генератора случайных чисел для синтетических
    исполнителей — расхождение метрик объясняется только механизмом
    адаптации, а не случайным несовпадением поведения людей.
  - N циклов («семестров»), M seeds — параметры командной строки.
  - Метрики за цикл: escalated_fraction, late_fraction, fitness (T-40),
    число предложенных/принятых корректировок.
  - Критерий успеха: среднее escalated_fraction на последнем цикле в
    adaptive-режиме статистически ниже, чем в baseline, на ТЕХ ЖЕ seeds
    (парное сравнение — см. _summarize).

Ограничение дизайна — см. docstring experiment/params.py: shift_start и
review_duration в этом эксперименте обе моделируются как расширение
относительного окна таймера, а не сдвиг абсолютной календарной даты.

Запуск: python -m experiment.run_experiment --cycles 8 --seeds 5
"""
from __future__ import annotations

import csv
import random
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api.config import settings
from mining.control_points import EXPERIMENT_CONTROL_POINTS
from mining.conveyor import analyze_cycle
from mining.corrections import propose_corrections
from orchestrator import Orchestrator
from simgen.executor import ExecutorProfile
from simgen.run import run_cycle

from .params import ProcessParams, apply_corrections

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "experiment_process.bpmn"
BASELINE_PARAMS = ProcessParams(reminder_days=7, escalation_days=14)
N_INSTANCES = 30
MAX_DAYS = 90        # с запасом: escalation_days может вырасти за несколько циклов адаптации

# ВАЖНО: расширение окна (escalation_days) лечит только "опоздавших" —
# исполнителей, которые рано или поздно всё-таки завершат задачу, просто
# позже нормативного срока. "Истинный" no-show (delay=None, исполнитель не
# появится НИКОГДА) эскалируется при любой ширине окна — window-widening
# принципиально не может его исправить, это НЕИСПРАВИМЫЙ пол эскалаций.
# С дефолтным профилем исполнителя (delay_median_days=3) при
# escalation_days~14-23 почти вся масса задержек сосредоточена намного ниже
# 14 дней — то есть систематическая эскалация практически ЦЕЛИКОМ объясняется
# no-show, а не задержкой, и расширение окна не даёт эффекта (проверено
# эмпирически: ручной прогон 4×3 показал escalated_fraction практически
# одинаковым в baseline/adaptive despite escalation_days 14->23). Чтобы
# контур адаптации имел что лечить, доля исправимой задержки должна быть
# заметной: снижаем no_show и поднимаем медианную задержку ближе к
# исходному escalation_days.
NO_SHOW_PROBABILITY = 0.08
DELAY_MEDIAN_DAYS = 10.0
DELAY_SIGMA = 0.6


@dataclass
class CycleRecord:
    seed: int
    regime: str
    cycle: int
    reminder_days: int
    escalation_days: int
    n_cases: int
    escalated_fraction: float
    late_fraction: float
    fitness: float | None
    corrections_proposed: int
    corrections_accepted: int


def run_regime(base_seed: int, regime: str, n_cycles: int, adapt: bool) -> list[CycleRecord]:
    """regime — произвольная метка (для process_key/CSV); adapt=True включает
    применение корректировок к параметрам следующего цикла (adaptive),
    adapt=False держит параметры фиксированными (baseline)."""
    orch = Orchestrator(settings.database_url)
    params = BASELINE_PARAMS
    records: list[CycleRecord] = []

    for cycle in range(n_cycles):
        # Один и тот же под-seed для одного и того же (base_seed, cycle) в
        # ОБОИХ режимах — см. дизайн выше.
        rng = random.Random(base_seed * 1000 + cycle)
        executor = ExecutorProfile(
            no_show_probability=NO_SHOW_PROBABILITY,
            delay_median_days=DELAY_MEDIAN_DAYS,
            delay_sigma=DELAY_SIGMA,
        )

        process_key = f"experiment_{regime}_{base_seed}_{cycle}_{uuid.uuid4().hex[:4]}"
        cycle_start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=200 * cycle)

        run_cycle(
            orch, rng, executor, process_key, BPMN, "experiment_process",
            N_INSTANCES, cycle_start, MAX_DAYS,
            initial_data=params.as_initial_data(),
        )

        report = analyze_cycle(settings.database_url, process_key, BPMN, EXPERIMENT_CONTROL_POINTS)
        cp = report.control_points["review_request"]
        proposed = propose_corrections(report)
        accepted = proposed if adapt else []

        records.append(CycleRecord(
            seed=base_seed, regime=regime, cycle=cycle,
            reminder_days=params.reminder_days, escalation_days=params.escalation_days,
            n_cases=cp.n_cases, escalated_fraction=cp.escalated_fraction, late_fraction=cp.late_fraction,
            fitness=report.fitness, corrections_proposed=len(proposed), corrections_accepted=len(accepted),
        ))

        if accepted:
            params = apply_corrections(params, accepted)

    return records


def run_experiment(n_cycles: int, n_seeds: int) -> list[CycleRecord]:
    records: list[CycleRecord] = []
    for seed in range(n_seeds):
        records += run_regime(seed, "baseline", n_cycles, adapt=False)
        records += run_regime(seed, "adaptive", n_cycles, adapt=True)
    return records


def _last_cycle_by(records: list[CycleRecord], regime: str, n_cycles: int) -> dict[int, CycleRecord]:
    return {r.seed: r for r in records if r.regime == regime and r.cycle == n_cycles - 1}


def summarize(records: list[CycleRecord], n_cycles: int) -> str:
    """Парное сравнение baseline/adaptive на последнем цикле по каждому seed."""
    baseline_last = _last_cycle_by(records, "baseline", n_cycles)
    adaptive_last = _last_cycle_by(records, "adaptive", n_cycles)
    seeds = sorted(set(baseline_last) & set(adaptive_last))

    diffs = [adaptive_last[s].escalated_fraction - baseline_last[s].escalated_fraction for s in seeds]
    improved = sum(1 for d in diffs if d < 0)
    worsened = sum(1 for d in diffs if d > 0)
    tied = len(diffs) - improved - worsened
    mean_diff = sum(diffs) / len(diffs) if diffs else float("nan")

    lines = [
        f"Последний цикл (cycle={n_cycles - 1}), парное сравнение по {len(seeds)} seed(ам):",
        f"  среднее escalated_fraction: baseline={sum(baseline_last[s].escalated_fraction for s in seeds) / len(seeds):.3f}, "
        f"adaptive={sum(adaptive_last[s].escalated_fraction for s in seeds) / len(seeds):.3f}",
        f"  среднее (adaptive - baseline) по seed: {mean_diff:+.3f}",
        f"  адаптивный режим лучше в {improved}/{len(seeds)} seed(ах), хуже в {worsened}, без изменений в {tied}",
    ]
    return "\n".join(lines)


def write_csv(records: list[CycleRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(records[0]).keys()))
        writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Эксперимент: базовый режим vs адаптивный (T-51)")
    parser.add_argument("--cycles", type=int, default=8)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "results.csv")
    args = parser.parse_args()

    records = run_experiment(args.cycles, args.seeds)
    write_csv(records, args.out)
    print(f"Записей: {len(records)} -> {args.out}")
    print()
    print(summarize(records, args.cycles))

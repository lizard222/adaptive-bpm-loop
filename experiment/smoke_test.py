# -*- coding: utf-8 -*-
"""Смоук-тест эксперимента (D1-D3/T-50-T-51) — уменьшенный масштаб (быстрее,
чем «боевой» прогон run_experiment.py --cycles 8 --seeds 5).

Проверяет сам механизм, а не конкретные числа:
  - в baseline параметры процесса НИКОГДА не меняются (контур адаптации
    считает корректировки для сравнения, но не применяет);
  - в adaptive параметры РЕАЛЬНО меняются хотя бы раз за прогон
    (escalation_days растёт — иначе тест на маленьком масштабе бесполезен:
    механизм мог бы молча ничего не делать, и мы бы этого не заметили);
  - CSV пишется и читается корректно.

Запуск: python -m experiment.smoke_test
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from .run_experiment import BASELINE_PARAMS, run_experiment, summarize, write_csv

N_CYCLES = 3
N_SEEDS = 2


def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    records = run_experiment(N_CYCLES, N_SEEDS)
    check("получено записей ровно cycles*seeds*regimes", len(records) == N_CYCLES * N_SEEDS * 2)

    baseline = [r for r in records if r.regime == "baseline"]
    adaptive = [r for r in records if r.regime == "adaptive"]

    check("baseline: параметры не менялись ни разу (reminder_days)",
          all(r.reminder_days == BASELINE_PARAMS.reminder_days for r in baseline))
    check("baseline: параметры не менялись ни разу (escalation_days)",
          all(r.escalation_days == BASELINE_PARAMS.escalation_days for r in baseline))
    check("baseline: корректировки никогда не применялись (только считались)",
          all(r.corrections_accepted == 0 for r in baseline))
    check("baseline: но корректировки хотя бы иногда ПРЕДЛАГАЛИСЬ (диагностика жива)",
          any(r.corrections_proposed > 0 for r in baseline))

    check("adaptive: escalation_days реально вырос хотя бы у одного seed",
          any(r.escalation_days > BASELINE_PARAMS.escalation_days for r in adaptive))
    check("adaptive: параметры внутри одного seed не убывают со временем (только растут)",
          all(
              adaptive[i].escalation_days <= adaptive[i + 1].escalation_days
              for i in range(len(adaptive) - 1)
              if adaptive[i].seed == adaptive[i + 1].seed
          ))

    out = Path(__file__).parent / "_smoke_results.csv"
    write_csv(records, out)
    with open(out, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    check("CSV записан и читается обратно с тем же числом строк", len(rows) == len(records))

    print()
    print(summarize(records, N_CYCLES))

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

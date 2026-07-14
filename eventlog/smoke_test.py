# -*- coding: utf-8 -*-
"""Смоук-тест экспорта XES (B2/T-32): round-trip запись->чтение через pm4py.

Запуск: сначала python -m orchestrator.smoke_test (чтобы в event_log были
данные), затем  python -m eventlog.smoke_test
"""
import sys
import tempfile
from pathlib import Path

import pm4py

from api.config import settings

from .xes_export import export_xes


def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "roundtrip.xes"
        n_exported = export_xes(settings.database_url, out, process_key="demo_process")
        check("файл XES создан и не пуст", out.exists() and out.stat().st_size > 0)

        log = pm4py.read_xes(str(out))
        check("pm4py читает файл без ошибок", log is not None and len(log) > 0)
        check("число событий совпадает с экспортированным", len(log) == n_exported)

        activities = set(log["concept:name"])
        check("бизнес-активности на месте", {"auto_step", "review_request", "remind"}.issubset(activities))
        check("служебных задач движка нет (фильтр T-31 работает)",
              not any("BoundaryEvent" in a or "EndJoin" in a for a in activities))

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

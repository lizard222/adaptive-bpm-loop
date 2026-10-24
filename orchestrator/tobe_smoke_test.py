# -*- coding: utf-8 -*-
"""Смоук-тест: to-be модель «Защита ВКР» (bpmn/tobe/vkr_defense_tobe.bpmn,
T-22) реально исполняется настоящим оркестратором — с PostgreSQL,
сериализацией после каждого шага и журналом событий, а не только разбирается
парсером.

Два выпуска по двое студентов: бакалавриат и магистратура. Проходит все
READY-задачи до конца и проверяет развилки: шаги только для магистратуры /
только для бакалавриата, подпроцесс по каждому студенту, изменение темы и
выговор — ровно одному студенту из двух, дорожка у каждой задачи.
process_key уникален на прогон — в "боевую" статистику не попадает.

Запуск: python -m orchestrator.tobe_smoke_test
"""
from __future__ import annotations

import sys
import uuid
from collections import Counter
from pathlib import Path

from api.config import settings
from orchestrator import Orchestrator

BPMN = Path(__file__).resolve().parents[1] / "bpmn" / "tobe" / "vkr_defense_tobe.bpmn"
RUN_ID = uuid.uuid4().hex[:6]
STUDENTS = ["Студент-1", "Студент-2"]

MASTER_ONLY = {"publication_plan", "individual_plans", "supervisor_review", "handover_to_gek", "docs_check"}
BACHELOR_ONLY = {"honors", "gek_payment"}


def run_cohort(orch: Orchestrator, level: str) -> tuple[Counter, bool, set]:
    case_id = f"tobe_{level}_{RUN_ID}"
    orch.start_instance(
        case_id, f"vkr_defense_tobe_test_{RUN_ID}", BPMN, "vkr_defense_tobe",
        initial_data={
            "level": level, "students": STUDENTS,
            "topics_days": 14, "normcontrol_days": 3, "plagiarism_days": 3, "admission_days": 5,
            "topic_change_needed": False, "report_2_ok": True,
        },
    )
    done: Counter = Counter()
    lanes_missing: set = set()
    for _ in range(200):
        state = orch.get_state(case_id)
        ready = [t for t in state["tasks"] if t["state"] == "READY"]
        if state["completed"] or not ready:
            break
        task = ready[0]
        if not task.get("lane"):
            lanes_missing.add(task["name"])
        data = None
        # первому из двух студентов — изменение темы и проваленная предзащита
        if task["name"] == "report_1" and done["report_1"] == 0:
            data = {"topic_change_needed": True}
        if task["name"] == "report_2" and done["report_2"] == 0:
            data = {"report_2_ok": False}
        orch.complete_task(case_id, task["name"], data=data, resource="tobe-smoke")
        done[task["name"]] += 1
    return done, orch.get_state(case_id)["completed"], lanes_missing


def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    orch = Orchestrator(settings.database_url)
    for level in ("bachelor", "master"):
        done, completed, lanes_missing = run_cohort(orch, level)
        print(f"-- {level}: выполнено шагов {sum(done.values())}")
        check(f"[{level}] выпуск дошёл до конца", completed)
        check(f"[{level}] у каждой READY-задачи есть дорожка (роль)", not lanes_missing)
        check(f"[{level}] подпроцесс отработал для каждого студента (по 2 отчёта и 2 защиты)",
              done["report_1"] == 2 and done["report_2"] == 2 and done["defense"] == 2)
        check(f"[{level}] изменение темы — ровно одному студенту", done["topic_change_order"] == 1)
        check(f"[{level}] выговор — ровно одному студенту", done["reprimand"] == 1)
        check(f"[{level}] шаги уровня выпуска — по одному разу",
              done["approve_topics"] == 1 and done["organize_defenses"] == 1 and done["archive"] == 1)
        if level == "master":
            check("[master] магистерские шаги пройдены", all(done[t] > 0 for t in MASTER_ONLY))
            check("[master] бакалаврских шагов нет", not any(done[t] for t in BACHELOR_ONLY))
        else:
            check("[bachelor] бакалаврские шаги пройдены", all(done[t] > 0 for t in BACHELOR_ONLY))
            check("[bachelor] магистерских шагов нет", not any(done[t] for t in MASTER_ONLY))

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

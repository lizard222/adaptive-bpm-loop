# -*- coding: utf-8 -*-
"""Спайк для D1/T-50: параметризация длительности BPMN-таймера через
переменную процесса (reminder_days), без переписывания BPMN-файла.

Если работает — контур адаптации сможет менять нормативные сроки между
циклами эксперимента (T-51) через orchestrator.start_instance(initial_data=...),
а не генерацией нового BPMN на каждый цикл.
"""
import sys
from datetime import timedelta
from pathlib import Path

from freezegun import freeze_time
from lxml import etree
from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow

try:
    from SpiffWorkflow.util.task import TaskState
except ImportError:
    from SpiffWorkflow.task import TaskState

BPMN = Path(__file__).parent / "parametrized_timer.bpmn"

checks: list[tuple[str, bool]] = []


def check(label: str, cond: bool) -> None:
    checks.append((label, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + label)


def state(wf, name) -> list[str]:
    def n(s):
        try:
            return TaskState.get_name(s)
        except Exception:
            return str(s)
    return [n(t.state) for t in wf.get_tasks() if t.task_spec.name == name] or ["<absent>"]


def make_spec():
    parser = BpmnParser()
    parser.add_bpmn_xml(etree.parse(str(BPMN)), filename=str(BPMN))
    return parser.get_spec("param_timer")


# --- Сценарий 1: reminder_days=3 -> должен сработать к дню 3, не к дню 7 ---
with freeze_time("2026-01-01") as frozen:
    wf = BpmnWorkflow(make_spec())
    wf.task_tree.data.update({"reminder_days": 3})
    wf.do_engine_steps()
    check("параметр 3 дня: задача READY на старте", "READY" in state(wf, "wait_task"))

    frozen.tick(timedelta(days=2))
    wf.refresh_waiting_tasks()
    wf.do_engine_steps()
    check("параметр 3 дня: день 2 — ещё не сработало", "COMPLETED" not in state(wf, "remind"))

    frozen.tick(timedelta(days=2))  # итого день 4
    wf.refresh_waiting_tasks()
    wf.do_engine_steps()
    check("параметр 3 дня: день 4 — сработало (уложились в 3 дня, не в 7 по умолчанию)",
          "COMPLETED" in state(wf, "remind"))

# --- Сценарий 2: reminder_days=10 -> не должен сработать раньше дня 10 ---
with freeze_time("2026-01-01") as frozen:
    wf2 = BpmnWorkflow(make_spec())
    wf2.task_tree.data.update({"reminder_days": 10})
    wf2.do_engine_steps()

    frozen.tick(timedelta(days=4))
    wf2.refresh_waiting_tasks()
    wf2.do_engine_steps()
    check("параметр 10 дней: день 4 — ещё не сработало (было бы сработало при дефолте 3)",
          "COMPLETED" not in state(wf2, "remind"))

    frozen.tick(timedelta(days=7))  # итого день 11
    wf2.refresh_waiting_tasks()
    wf2.do_engine_steps()
    check("параметр 10 дней: день 11 — сработало", "COMPLETED" in state(wf2, "remind"))

print(f"\nИтого: {sum(1 for _, ok in checks if ok)}/{len(checks)} проверок пройдено")
sys.exit(0 if all(ok for _, ok in checks) else 1)

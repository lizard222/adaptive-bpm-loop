# -*- coding: utf-8 -*-
"""Спайк для T-35: можно ли "перемотать" таймеры SpiffWorkflow без реального
ожидания? Нормативные сроки процессов кафедры измеряются днями/неделями
("за 14 дней до ГЭК") — крутить восемь виртуальных семестров в реальном
времени нереально.

SpiffWorkflow (timer.py) везде использует datetime.now(timezone.utc) напрямую,
без инъекции часов. Проверяем, ловит ли freezegun (патчит datetime.datetime
глобально, включая уже импортированные модули) эти вызовы.
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

BPMN = Path(__file__).parents[1] / "sim_clock_spike" / "long_timer.bpmn"

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


parser = BpmnParser()
parser.add_bpmn_xml(etree.parse(str(BPMN)), filename=str(BPMN))
spec = parser.get_spec("long_timer")

with freeze_time("2026-01-01 00:00:00") as frozen:
    wf = BpmnWorkflow(spec)
    wf.do_engine_steps()
    check("задача READY в момент старта (2026-01-01)", "READY" in state(wf, "wait_task"))

    frozen.tick(timedelta(days=13))
    wf.refresh_waiting_tasks()
    wf.do_engine_steps()
    check("день 13: таймер P14D ещё НЕ сработал", "COMPLETED" not in state(wf, "remind_14d"))

    frozen.tick(timedelta(days=2))  # итого 15 дней от старта
    wf.refresh_waiting_tasks()
    wf.do_engine_steps()
    check("день 15: таймер P14D сработал БЕЗ реального ожидания", "COMPLETED" in state(wf, "remind_14d"))

print(f"\nИтого: {sum(1 for _, ok in checks if ok)}/{len(checks)} проверок пройдено")
sys.exit(0 if all(ok for _, ok in checks) else 1)

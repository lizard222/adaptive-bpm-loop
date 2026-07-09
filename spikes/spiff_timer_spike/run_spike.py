# -*- coding: utf-8 -*-
"""Спайк T-28: тянет ли SpiffWorkflow граничные таймеры и эскалации (риск из spec §10).

Сценарий 1: исполнитель молчит -> через 2с non-interrupting напоминание,
            через 4с interrupting эскалация отменяет задачу, процесс завершается.
Сценарий 2: исполнитель выполняет задачу сразу -> таймеры не срабатывают.
"""
import sys
import time
from pathlib import Path

import SpiffWorkflow
from lxml import etree
from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow

try:
    from SpiffWorkflow.util.task import TaskState
except ImportError:  # старые версии
    from SpiffWorkflow.task import TaskState

HERE = Path(__file__).parent


def make_wf() -> BpmnWorkflow:
    parser = BpmnParser()
    # ВАЖНО (Windows): add_bpmn_file открывает файл в системной кодировке (cp1251)
    # и падает на кириллице в UTF-8. Загружаем XML через lxml — он читает байты
    # и берёт кодировку из XML-декларации.
    path = HERE / "vkr_fragment.bpmn"
    parser.add_bpmn_xml(etree.parse(str(path)), filename=str(path))
    return BpmnWorkflow(parser.get_spec("spike_vkr_fragment"))


def pump(wf: BpmnWorkflow) -> None:
    wf.refresh_waiting_tasks()
    wf.do_engine_steps()


def states(wf: BpmnWorkflow, spec_name: str) -> list[str]:
    def name(state):
        try:
            return TaskState.get_name(state)
        except Exception:
            return str(state)
    return [name(t.state) for t in wf.get_tasks() if t.task_spec.name == spec_name] or ["<absent>"]


checks: list[tuple[str, bool]] = []


def check(label: str, cond: bool) -> None:
    checks.append((label, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + label)


print("SpiffWorkflow", getattr(SpiffWorkflow, "__version__", "?"))
print()
print("=== Сценарий 1: исполнитель молчит (напоминание, затем эскалация) ===")
wf = make_wf()
wf.do_engine_steps()
check("userTask READY на старте", "READY" in states(wf, "prepare_order"))
check("напоминание ещё не сработало", "COMPLETED" not in states(wf, "remind"))

time.sleep(2.5)
pump(wf)
check("~2.5с: non-interrupting таймер сработал (напоминание COMPLETED)", "COMPLETED" in states(wf, "remind"))
check("~2.5с: userTask по-прежнему READY (напоминание её не отменило)", "READY" in states(wf, "prepare_order"))

time.sleep(2.0)
pump(wf)
check("~4.5с: interrupting таймер сработал (эскалация COMPLETED)", "COMPLETED" in states(wf, "escalate"))
check("~4.5с: userTask отменена эскалацией (CANCELLED)", "CANCELLED" in states(wf, "prepare_order"))
check("процесс завершён по ветке эскалации", wf.is_completed())
check("данные процесса: escalated == True", wf.data.get("escalated") is True)
# ВЫВОД СПАЙКА: данные ветки non-interrupting события НЕ сливаются в общие данные
# процесса (ветки изолированы — корректная семантика BPMN). Факты типа "напоминание
# отправлено" должны фиксироваться в event_log, а не в переменных процесса.
check("семантика данных: reminder_fired ветки не попал в общие данные (изоляция веток)",
      wf.data.get("reminder_fired") is not True)

print()
print("=== Сценарий 2: исполнитель выполняет задачу сразу ===")
wf2 = make_wf()
wf2.do_engine_steps()
ready = [t for t in wf2.get_tasks(state=TaskState.READY) if t.task_spec.name == "prepare_order"]
check("нашли READY userTask", len(ready) == 1)
ready[0].run()
wf2.do_engine_steps()
check("процесс завершён сразу после выполнения задачи", wf2.is_completed())
check("напоминание не срабатывало", wf2.data.get("reminder_fired") is False)
check("эскалации не было", wf2.data.get("escalated") is False)

print()
failed = [label for label, ok in checks if not ok]
print(f"Итого: {len(checks) - len(failed)}/{len(checks)} проверок пройдено")
sys.exit(1 if failed else 0)

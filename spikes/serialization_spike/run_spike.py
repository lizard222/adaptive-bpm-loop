# -*- coding: utf-8 -*-
"""Спайк сериализации для оркестратора (T-31): переживает ли BpmnWorkflow
с АКТИВНЫМИ таймерами перезапуск процесса, если состояние хранится в PostgreSQL.

Сценарий:
  1. Запустить workflow (переиспользуем фрагмент из спайка T-28: userTask +
     non-interrupting напоминание (2с) + interrupting эскалация (4с)).
  2. Сериализовать в JSON сразу после старта (таймеры ещё не сработали) и
     записать в PostgreSQL (process_instances.state).
  3. УНИЧТОЖИТЬ объект workflow в памяти (имитация рестарта процесса Python).
  4. Прочитать JSON из PostgreSQL, десериализовать в новый объект workflow.
  5. Подождать и убедиться, что таймеры на восстановленном объекте всё ещё
     срабатывают по прежнему графику (напоминание к ~2с, эскалация к ~4с от
     МОМЕНТА СОЗДАНИЯ, а не от момента восстановления).
"""
import sys
import time
from pathlib import Path

import psycopg
from lxml import etree
from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser
from SpiffWorkflow.bpmn.serializer.workflow import BpmnWorkflowSerializer
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow

try:
    from SpiffWorkflow.util.task import TaskState
except ImportError:
    from SpiffWorkflow.task import TaskState

sys.path.insert(0, str(Path(__file__).parents[2]))
from api.config import settings  # noqa: E402

BPMN_FILE = Path(__file__).parents[1] / "spiff_timer_spike" / "vkr_fragment.bpmn"
SERIALIZER = BpmnWorkflowSerializer()

checks: list[tuple[str, bool]] = []


def check(label: str, cond: bool) -> None:
    checks.append((label, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + label)


def states(wf: BpmnWorkflow, spec_name: str) -> list[str]:
    def name(state):
        try:
            return TaskState.get_name(state)
        except Exception:
            return str(state)
    return [name(t.state) for t in wf.get_tasks() if t.task_spec.name == spec_name] or ["<absent>"]


def make_spec():
    parser = BpmnParser()
    parser.add_bpmn_xml(etree.parse(str(BPMN_FILE)), filename=str(BPMN_FILE))
    return parser.get_spec("spike_vkr_fragment")


def ensure_table(conn: psycopg.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS process_instances_spike (
            case_id TEXT PRIMARY KEY,
            state   JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.commit()


print("=== Спайк сериализации: PostgreSQL как хранилище состояния оркестратора ===\n")

conn = psycopg.connect(settings.database_url)
ensure_table(conn)
conn.execute("DELETE FROM process_instances_spike WHERE case_id = 'ser-spike-1'")
conn.commit()

# 1. Запуск
wf = BpmnWorkflow(make_spec())
wf.do_engine_steps()
check("процесс стартовал, userTask READY", "READY" in states(wf, "prepare_order"))

# 2. Сериализация -> запись в PostgreSQL
payload = SERIALIZER.serialize_json(wf)
conn.execute(
    "INSERT INTO process_instances_spike (case_id, state) VALUES (%s, %s)",
    ("ser-spike-1", payload),
)
conn.commit()
check("состояние записано в PostgreSQL", True)

# 3. "Убиваем" объект в памяти
del wf

# 4. Восстановление из PostgreSQL как после рестарта процесса
row = conn.execute(
    "SELECT state::text FROM process_instances_spike WHERE case_id = %s", ("ser-spike-1",)
).fetchone()
restored_json = row[0]
wf2 = SERIALIZER.deserialize_json(restored_json)
check("объект workflow восстановлен из JSON", isinstance(wf2, BpmnWorkflow))
check("после восстановления userTask всё ещё READY", "READY" in states(wf2, "prepare_order"))

# 5. Таймеры на восстановленном объекте продолжают идти по исходному графику
time.sleep(2.5)
wf2.refresh_waiting_tasks()
wf2.do_engine_steps()
check("~2.5с от старта: напоминание сработало НА ВОССТАНОВЛЕННОМ объекте",
      "COMPLETED" in states(wf2, "remind"))
check("~2.5с: userTask всё ещё READY (напоминание не отменяет)", "READY" in states(wf2, "prepare_order"))

time.sleep(2.0)
wf2.refresh_waiting_tasks()
wf2.do_engine_steps()
check("~4.5с от старта: эскалация сработала на восстановленном объекте",
      "COMPLETED" in states(wf2, "escalate"))
check("~4.5с: userTask отменена эскалацией", "CANCELLED" in states(wf2, "prepare_order"))
check("процесс завершён после восстановления", wf2.is_completed())

# Финальное состояние тоже сериализуется (проверка полного цикла для завершённого процесса)
final_payload = SERIALIZER.serialize_json(wf2)
conn.execute(
    "UPDATE process_instances_spike SET state = %s, updated_at = now() WHERE case_id = %s",
    (final_payload, "ser-spike-1"),
)
conn.commit()
check("финальное состояние (завершённый процесс) тоже сериализуется", True)

conn.close()

print()
failed = [label for label, ok in checks if not ok]
print(f"Итого: {len(checks) - len(failed)}/{len(checks)} проверок пройдено")
sys.exit(1 if failed else 0)

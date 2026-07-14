"""Оркестратор процессов (T-31, ФТ-С-3).

MVP: ведёт экземпляры BPMN как конечные автоматы SpiffWorkflow, сериализует
состояние в PostgreSQL после каждого изменения (ФТ-С-3.3, находки —
spikes/serialization_spike/FINDINGS.md) и пишет событие в event_log на каждое
значимое изменение состояния (ФТ-С-3.2, ФТ-С-5.1).

Не входит в MVP (следующие задачи): назначение задач интерфейсным агентам
(FIPA Request) — сейчас есть только complete_task() для прямого вызова;
конкретные модели процессов кафедры (T-22/T-23) — оркестратор моделе-агностичен,
принимает произвольный BPMN-файл.
"""
from __future__ import annotations

from pathlib import Path

import psycopg
from SpiffWorkflow.bpmn.serializer.workflow import BpmnWorkflowSerializer
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow

try:
    from SpiffWorkflow.util.task import TaskState
except ImportError:
    from SpiffWorkflow.task import TaskState

from .specs import load_spec

_SERIALIZER = BpmnWorkflowSerializer()


class InstanceNotFound(Exception):
    pass


class TaskNotReady(Exception):
    pass


def _task_state_name(state) -> str:
    try:
        return TaskState.get_name(state)
    except Exception:
        return str(state)


def _snapshot(wf: BpmnWorkflow) -> dict[str, str]:
    """id задачи -> имя состояния, для выявления переходов между тиками."""
    return {str(t.id): _task_state_name(t.state) for t in wf.get_tasks()}


# Настоящие элементы BPMN (задачи, события, шлюзы) реализованы в
# SpiffWorkflow.bpmn.specs.defaults; служебная бухгалтерия движка для сборки
# графа (BoundaryEventSplit/Join, _EndJoin, обёртки Start/End) — в
# SpiffWorkflow.bpmn.specs.control. Без фильтра event_log засоряется этими
# псевдо-задачами и искажает discovery в интеллектуальном анализе (ФТ-С-7.1).
_LOGGABLE_SPEC_MODULE = "SpiffWorkflow.bpmn.specs.defaults"


def _is_business_activity(task) -> bool:
    return type(task.task_spec).__module__ == _LOGGABLE_SPEC_MODULE


class Orchestrator:
    def __init__(self, database_url: str):
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._database_url)

    # ---------- персистентность ----------

    def _persist(self, conn: psycopg.Connection, case_id: str, process_key: str, wf: BpmnWorkflow) -> None:
        status = "completed" if wf.is_completed() else "active"
        payload = _SERIALIZER.serialize_json(wf)
        conn.execute(
            """
            INSERT INTO process_instances (case_id, process_key, status, state, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (case_id) DO UPDATE
                SET status = EXCLUDED.status, state = EXCLUDED.state, updated_at = now()
            """,
            (case_id, process_key, status, payload),
        )

    def _load(self, conn: psycopg.Connection, case_id: str) -> tuple[BpmnWorkflow, str]:
        row = conn.execute(
            "SELECT process_key, state::text FROM process_instances WHERE case_id = %s", (case_id,)
        ).fetchone()
        if row is None:
            raise InstanceNotFound(case_id)
        process_key, state_json = row
        return _SERIALIZER.deserialize_json(state_json), process_key

    def _log_event(
        self,
        conn: psycopg.Connection,
        case_id: str,
        process_key: str,
        activity: str,
        lifecycle: str = "complete",
        resource: str | None = None,
        attributes: dict | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO event_log (case_id, process_key, activity, lifecycle, resource, attributes)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (case_id, process_key, activity, lifecycle, resource, psycopg.types.json.Json(attributes or {})),
        )

    def _log_transitions(
        self, conn: psycopg.Connection, case_id: str, process_key: str, before: dict, wf: BpmnWorkflow
    ) -> None:
        """Сравнивает состояния задач до/после engine-степа, пишет событие на каждый
        переход в COMPLETED или CANCELLED (ФТ-С-5.1)."""
        after = _snapshot(wf)
        for task in wf.get_tasks():
            if not _is_business_activity(task):
                continue
            tid = str(task.id)
            prev = before.get(tid)
            cur = after.get(tid)
            if prev != cur and cur in ("COMPLETED", "CANCELLED"):
                self._log_event(
                    conn, case_id, process_key, task.task_spec.name,
                    lifecycle=cur.lower(), resource="orchestrator",
                )
        if wf.is_completed():
            self._log_event(conn, case_id, process_key, "process_instance", lifecycle="complete",
                             resource="orchestrator")

    # ---------- публичный API ----------

    def start_instance(self, case_id: str, process_key: str, bpmn_file: Path, process_id: str | None = None,
                        initial_data: dict | None = None) -> None:
        spec = load_spec(bpmn_file, process_id)
        wf = BpmnWorkflow(spec)
        if initial_data:
            wf.data.update(initial_data)
        before = _snapshot(wf)
        wf.do_engine_steps()
        with self._connect() as conn:
            self._log_event(conn, case_id, process_key, "process_instance", lifecycle="start",
                             resource="orchestrator")
            self._log_transitions(conn, case_id, process_key, before, wf)
            self._persist(conn, case_id, process_key, wf)
            conn.commit()

    def tick(self, case_id: str) -> None:
        """Проверяет таймеры и продвигает экземпляр (см. FINDINGS T-28: таймеры пассивны,
        требуют периодического refresh)."""
        with self._connect() as conn:
            wf, process_key = self._load(conn, case_id)
            before = _snapshot(wf)
            wf.refresh_waiting_tasks()
            wf.do_engine_steps()
            self._log_transitions(conn, case_id, process_key, before, wf)
            self._persist(conn, case_id, process_key, wf)
            conn.commit()

    def tick_all(self) -> int:
        """Тикает все активные экземпляры. Возвращает их число."""
        with self._connect() as conn:
            case_ids = [r[0] for r in conn.execute(
                "SELECT case_id FROM process_instances WHERE status = 'active'"
            ).fetchall()]
        for case_id in case_ids:
            self.tick(case_id)
        return len(case_ids)

    def complete_task(self, case_id: str, task_name: str, data: dict | None = None,
                       resource: str | None = None) -> None:
        """Выполняет READY-задачу по имени (заглушка ФТ-С-4: реальное назначение
        через интерфейсных агентов — отдельная задача)."""
        with self._connect() as conn:
            wf, process_key = self._load(conn, case_id)
            ready = [t for t in wf.get_tasks(state=TaskState.READY) if t.task_spec.name == task_name]
            if not ready:
                raise TaskNotReady(f"{task_name} не в состоянии READY для {case_id}")
            task = ready[0]
            if data:
                task.data.update(data)
            task.run()
            before = _snapshot(wf)
            wf.do_engine_steps()
            self._log_event(conn, case_id, process_key, task_name, lifecycle="complete", resource=resource)
            self._log_transitions(conn, case_id, process_key, before, wf)
            self._persist(conn, case_id, process_key, wf)
            conn.commit()

    def get_state(self, case_id: str) -> dict:
        with self._connect() as conn:
            wf, process_key = self._load(conn, case_id)
        return {
            "case_id": case_id,
            "process_key": process_key,
            "completed": wf.is_completed(),
            "tasks": [
                {"name": t.task_spec.name, "state": _task_state_name(t.state)}
                for t in wf.get_tasks() if t.task_spec.name
            ],
            "data": dict(wf.data),
        }

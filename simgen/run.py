"""Генератор синтетических журналов v1 (T-35, ФТ-С-9): прогоняет цикл процесса
на синтетических исполнителях с управляемым виртуальным временем (freezegun —
см. spikes/sim_clock_spike/FINDINGS.md, без этого таймеры в днях/неделях
пришлось бы ждать по-настоящему) и фиксируемым seed (ФТ-С-9.2).

Шаг симуляции — виртуальные сутки: для процессов кафедры (сроки в днях и
неделях, не в минутах) этого достаточно и заметно проще, чем вычислять точный
момент следующего срабатывания таймера внутри SpiffWorkflow.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from freezegun import freeze_time

from orchestrator import Orchestrator

from .executor import ExecutorProfile


@dataclass
class CycleReport:
    process_key: str
    started: int
    completed: int
    still_active: int
    reminders: int
    escalations: int
    mean_duration_days: float | None

    def __str__(self) -> str:  # удобный вывод для CLI
        md = f"{self.mean_duration_days:.1f}" if self.mean_duration_days is not None else "—"
        return (
            f"{self.process_key}: запущено {self.started}, завершено {self.completed}, "
            f"активно осталось {self.still_active}, напоминаний {self.reminders}, "
            f"эскалаций {self.escalations}, средняя длительность {md} дн."
        )


def run_cycle(
    orch: Orchestrator,
    rng: random.Random,
    executor: ExecutorProfile,
    process_key: str,
    bpmn_file: Path,
    process_id: str,
    n_instances: int,
    cycle_start: datetime,
    max_days: int,
    reminder_activities: tuple[str, ...] = ("remind",),
    escalation_activities: tuple[str, ...] = ("escalate",),
) -> CycleReport:
    """Запускает n_instances экземпляров процесса в один виртуальный день и
    прогоняет их до max_days виртуальных суток включительно.

    reminder_activities/escalation_activities — имена активностей-таймеров
    для итогового отчёта (по умолчанию — как в demo_process_days.bpmn с одной
    контрольной точкой; для процессов с несколькими контрольными точками,
    например bpmn/demo/workload_planning_days.bpmn, нужно передать полный
    список: без этого счётчики reminders/escalations в CycleReport будут
    молча нулевыми — найдено при подключении второго процесса, B6/T-38."""
    case_ids: list[str] = []

    with freeze_time(cycle_start) as frozen:
        for i in range(n_instances):
            case_id = f"{process_key}-{cycle_start:%Y%m%d}-{i:04d}-{uuid.uuid4().hex[:4]}"
            orch.start_instance(case_id, process_key, bpmn_file, process_id)
            case_ids.append(case_id)

        # (case_id, имя задачи) -> день выполнения синтетическим исполнителем,
        # либо None — исполнитель не появится вовсе (систематический пропуск).
        scheduled: dict[tuple[str, str], int | None] = {}

        for day in range(max_days + 1):
            frozen.move_to(cycle_start + timedelta(days=day))
            orch.tick_all()  # резолвит таймеры BPMN, сработавшие к этому дню

            for case_id in case_ids:
                state = orch.get_state(case_id)
                if state["completed"]:
                    continue
                for task in state["tasks"]:
                    if task["state"] != "READY":
                        continue
                    key = (case_id, task["name"])
                    if key not in scheduled:
                        delay = executor.sample_delay_days(rng)
                        scheduled[key] = None if delay is None else day + round(delay)
                    if scheduled[key] == day:
                        orch.complete_task(case_id, task["name"], resource="synthetic")

    return _collect_report(orch, process_key, case_ids, reminder_activities, escalation_activities)


def _collect_report(
    orch: Orchestrator, process_key: str, case_ids: list[str],
    reminder_activities: tuple[str, ...] = ("remind",),
    escalation_activities: tuple[str, ...] = ("escalate",),
) -> CycleReport:
    states = {c: orch.get_state(c) for c in case_ids}
    completed_ids = [c for c, s in states.items() if s["completed"]]

    with psycopg.connect(orch.database_url) as conn:
        # Фильтр по case_id обязателен: process_key может повторяться между
        # прогонами (например, в тесте на воспроизводимость по seed) — без
        # него счётчики задвоились бы событиями чужого прогона.
        reminders = conn.execute(
            "SELECT count(*) FROM event_log WHERE process_key=%s AND case_id = ANY(%s) "
            "AND activity = ANY(%s) AND lifecycle='completed'",
            (process_key, case_ids, list(reminder_activities)),
        ).fetchone()[0]
        escalations = conn.execute(
            "SELECT count(*) FROM event_log WHERE process_key=%s AND case_id = ANY(%s) "
            "AND activity = ANY(%s) AND lifecycle='completed'",
            (process_key, case_ids, list(escalation_activities)),
        ).fetchone()[0]
        rows = conn.execute(
            """
            SELECT case_id, extract(epoch FROM max(ts) - min(ts)) / 86400.0
            FROM event_log WHERE process_key = %s AND case_id = ANY(%s)
            GROUP BY case_id
            """,
            (process_key, case_ids),
        ).fetchall()

    duration_by_case = {c: float(d) for c, d in rows}
    finished_durations = [duration_by_case[c] for c in completed_ids if c in duration_by_case]

    return CycleReport(
        process_key=process_key,
        started=len(case_ids),
        completed=len(completed_ids),
        still_active=len(case_ids) - len(completed_ids),
        reminders=reminders,
        escalations=escalations,
        mean_duration_days=(sum(finished_durations) / len(finished_durations)) if finished_durations else None,
    )


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1]))
    from api.config import settings  # noqa: E402

    parser = argparse.ArgumentParser(description="Генератор синтетических журналов (T-35)")
    parser.add_argument("--process-key", default="demo_process_days")
    parser.add_argument("--bpmn", type=Path, default=Path(__file__).parents[1] / "bpmn" / "demo" / "demo_process_days.bpmn")
    parser.add_argument("--process-id", default="demo_process_days")
    parser.add_argument("--instances", type=int, default=20)
    parser.add_argument("--max-days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-show-probability", type=float, default=0.15)
    args = parser.parse_args()

    orchestrator = Orchestrator(settings.database_url)
    rng = random.Random(args.seed)
    executor = ExecutorProfile(no_show_probability=args.no_show_probability)
    report = run_cycle(
        orchestrator, rng, executor, args.process_key, args.bpmn, args.process_id,
        args.instances, datetime(2026, 10, 1, tzinfo=timezone.utc), args.max_days,
    )
    print(report)

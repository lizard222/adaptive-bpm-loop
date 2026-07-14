"""Агент Планировщик (T-33, ФТ-А-П-1..4): запускает экземпляры процессов по
расписанию и продвигает движок (тикает таймеры активных экземпляров).

Полная версионируемая таблица process_params (сроки запуска, календарь) — это
задача T-25; здесь минимальный эквивалент — LaunchRule с фиксированным
интервалом. Замена интервала на настоящий академический календарь при T-25 не
требует переписывать агента: меняется только реализация _is_due().

Продвижение движка (Orchestrator.tick_all — проверка сработавших таймеров BPMN,
находка спайка T-28) сделано частью того же периодического поведения, а не
вынесено в отдельного агента: кто-то должен тикать регулярно, и Планировщик уже
для этого просыпается.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("agents.scheduler")

import psycopg
from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour
from spade.message import Message

from orchestrator import Orchestrator


@dataclass
class LaunchRule:
    process_key: str
    bpmn_file: Path
    process_id: str
    interval_seconds: float  # демо-эквивалент академического календаря (T-25)
    param_version: int = 1


class SchedulerAgent(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        database_url: str,
        rules: list[LaunchRule],
        admin_jid: str | None = None,
        tick_seconds: float = 1.0,
    ):
        super().__init__(jid, password)
        self._database_url = database_url
        self._rules = rules
        self._admin_jid = admin_jid
        self._tick_seconds = tick_seconds
        self.orchestrator = Orchestrator(database_url)
        self.launched_case_ids: list[str] = []  # для наблюдения из тестов

    async def setup(self) -> None:
        self.add_behaviour(self.LaunchTick(period=self._tick_seconds))

    def _last_launch_ts(self, conn: psycopg.Connection, process_key: str) -> float | None:
        row = conn.execute(
            "SELECT extract(epoch from max(ts)) FROM event_log "
            "WHERE process_key=%s AND activity='process_instance' AND lifecycle='start'",
            (process_key,),
        ).fetchone()
        # psycopg отдаёт numeric из extract(epoch...) как decimal.Decimal, не float
        return float(row[0]) if row[0] is not None else None

    def _is_due(self, conn: psycopg.Connection, rule: LaunchRule) -> bool:
        last = self._last_launch_ts(conn, rule.process_key)
        return last is None or (time.time() - last) >= rule.interval_seconds

    class LaunchTick(PeriodicBehaviour):
        async def run(self) -> None:
            agent: SchedulerAgent = self.agent

            # Продвигаем движок: проверяем таймеры всех активных экземпляров
            # (ФТ-С-3, находка спайка T-28 — таймеры пассивны без этого вызова).
            agent.orchestrator.tick_all()

            with psycopg.connect(agent._database_url) as conn:
                due = [r for r in agent._rules if agent._is_due(conn, r)]

            for rule in due:
                case_id = f"{rule.process_key}-{uuid.uuid4().hex[:8]}"
                try:
                    agent.orchestrator.start_instance(
                        case_id, rule.process_key, rule.bpmn_file, rule.process_id,
                        attributes={"param_version": rule.param_version},
                    )
                    agent.launched_case_ids.append(case_id)
                except Exception as exc:  # ФТ-А-П-4: отказ -> сообщение админу, повтор на следующем тике
                    logger.error("Не удалось запустить %s (%s): %s", rule.process_key, case_id, exc)
                    if agent._admin_jid:
                        msg = Message(to=agent._admin_jid)
                        msg.set_metadata("performative", "refuse")
                        msg.body = f"Не удалось запустить {rule.process_key} ({case_id}): {exc}"
                        await self.send(msg)

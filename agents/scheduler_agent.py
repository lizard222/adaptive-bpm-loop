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

E3 (часть T-25): если у правила задан base_params (модель с параметризованными
таймерами, spikes/param_timer_spike/), Планировщик перед КАЖДЫМ запуском читает
process_params_current — актуальные параметры, обновляемые Аналитик-Адаптером
(T-42) — и передаёт их в start_instance(initial_data=...). Чтение всегда
свежее (pull), а не из кеша: агент переживает рестарт без потери состояния.
Приёмное поведение (ParamsListener) не хранит состояние само — оно только
подтверждает получение уведомления и логирует его; реальный эффект даёт
свежее чтение на каждом тике, уведомление лишь протокольно ожидаемо (ФТ-А-А-4).
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
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.message import Message

from experiment.params import ProcessParams
from orchestrator import Orchestrator

from .params_store import get_current_params


@dataclass
class LaunchRule:
    process_key: str
    bpmn_file: Path
    process_id: str
    interval_seconds: float  # демо-эквивалент академического календаря (T-25)
    param_version: int = 1
    base_params: ProcessParams | None = None  # None — модель без параметризованных таймеров


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
        self.received_notifications: list[dict] = []  # для наблюдения из тестов

    async def setup(self) -> None:
        self.add_behaviour(self.LaunchTick(period=self._tick_seconds))
        self.add_behaviour(self.ParamsListener())

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
                initial_data = None
                param_version = rule.param_version
                if rule.base_params is not None:
                    # Свежее чтение на каждом запуске (не кеш) — E3, см. докстринг модуля.
                    current = get_current_params(agent._database_url, rule.process_key, rule.base_params)
                    initial_data = current.as_initial_data()
                try:
                    agent.orchestrator.start_instance(
                        case_id, rule.process_key, rule.bpmn_file, rule.process_id,
                        initial_data=initial_data,
                        attributes={"param_version": param_version, "initial_data": initial_data},
                    )
                    agent.launched_case_ids.append(case_id)
                except Exception as exc:  # ФТ-А-П-4: отказ -> сообщение админу, повтор на следующем тике
                    logger.error("Не удалось запустить %s (%s): %s", rule.process_key, case_id, exc)
                    if agent._admin_jid:
                        msg = Message(to=agent._admin_jid)
                        msg.set_metadata("performative", "refuse")
                        msg.body = f"Не удалось запустить {rule.process_key} ({case_id}): {exc}"
                        await self.send(msg)

    class ParamsListener(CyclicBehaviour):
        """Приёмное поведение (ФТ-А-А-4, E3): подтверждает уведомление от
        Аналитик-Адаптера о новой версии параметров. Реальный эффект даёт не
        это поведение само по себе, а свежее чтение process_params_current в
        LaunchTick на каждом тике — уведомление лишь протокольно ожидаемо и
        полезно для логов/наблюдаемости (агент не полагается на то, что оно
        точно дойдёт: пропущенное уведомление не приведёт к устаревшим
        параметрам, следующий тик всё равно перечитает БД)."""

        async def run(self) -> None:
            msg = await self.receive(timeout=5)
            if msg is None or msg.get_metadata("event") != "process_params_updated":
                return
            self.agent.received_notifications.append({
                "process_key": msg.get_metadata("process_key"),
                "version": msg.get_metadata("version"),
                "body": msg.body,
            })
            logger.info("Получено уведомление о новой версии параметров: %s", msg.body)

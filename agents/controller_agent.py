"""Агент Контролер (T-34, ФТ-А-К-1..5): следит за контрольными точками и
уведомляет о напоминаниях/эскалациях.

Сами таймеры и их срабатывание реализованы в BPMN-модели поверх оркестратора
(граничные события, спайк T-28, доказано на живом движке) — Контролер не
дублирует эту механику. Его задача уже, но именно та, что описана в
требованиях: превратить свершившийся факт "таймер сработал" в уведомление
конкретному получателю (FIPA inform) и лестницу эскалации, не выполняя при
этом никаких действий за исполнителя (ФТ-А-К-5).

watch_activities сопоставляет id BPMN-задачи со "смыслом" контрольной точки
(например, {"remind": "напоминание", "escalate": "эскалация"}).

E3 (часть T-25): Контролер принимает уведомление от Аналитик-Адаптера о новой
версии параметров (ParamsListener) — до E3 не было ни одного receive-поведения.

E15 (ФТ-А-К-4, закрывает остаток T-25): если уведомление сообщает о новой
версии МОДЕЛИ (принятая add_checkpoint поставила контрольную точку на шаг),
Контролер начинает следить и за новой точкой. Раньше расширить
watch_activities было нечем: Correction знает только id шага. Теперь имена
активностей выводятся из id шага по соглашению
(mining.control_points.added_control_point), а сам список добавленных точек
Контролер перечитывает из БД (agents/model_store.py) — тело сообщения не
источник истины.
"""
from __future__ import annotations

import logging

import psycopg
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.message import Message

from mining.control_points import added_control_point

from .model_store import current_version

logger = logging.getLogger("agents.controller")


class ControllerAgent(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        database_url: str,
        watch_activities: dict[str, str],
        recipient_jid: str,
        tick_seconds: float = 1.0,
    ):
        super().__init__(jid, password)
        self._database_url = database_url
        self._watch = watch_activities
        self._recipient_jid = recipient_jid
        self._tick_seconds = tick_seconds
        self._last_event_id = 0
        self.dispatched: list[dict] = []  # для наблюдения из тестов
        self.received_notifications: list[dict] = []  # для наблюдения из тестов

    @property
    def watched_activities(self) -> dict[str, str]:
        return dict(self._watch)

    def watch_added_checkpoints(self, process_key: str) -> None:
        """E15: добавить в отслеживаемые точки текущей версии модели процесса."""
        _, added = current_version(self._database_url, process_key)
        for task in added:
            cp = added_control_point(task)
            self._watch.setdefault(cp.reminder_activity, "напоминание")
            self._watch.setdefault(cp.escalation_activity, "эскалация")
        logger.info("Контрольные точки %s (%s) добавлены в отслеживаемые", added, process_key)

    async def setup(self) -> None:
        with psycopg.connect(self._database_url) as conn:
            row = conn.execute("SELECT coalesce(max(event_id), 0) FROM event_log").fetchone()
            self._last_event_id = row[0]
        self.add_behaviour(self.Watch(period=self._tick_seconds))
        self.add_behaviour(self.ParamsListener())

    class ParamsListener(CyclicBehaviour):
        """Приёмное поведение (E3): подтверждает уведомление от Аналитик-
        Адаптера; при новой версии модели (E15) добавляет её контрольные
        точки в отслеживаемые."""

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
            if msg.get_metadata("model_version"):
                self.agent.watch_added_checkpoints(msg.get_metadata("process_key"))


    class Watch(PeriodicBehaviour):
        async def run(self) -> None:
            agent: ControllerAgent = self.agent
            with psycopg.connect(agent._database_url) as conn:
                rows = conn.execute(
                    "SELECT event_id, case_id, process_key, activity FROM event_log "
                    "WHERE event_id > %s AND lifecycle = 'completed' ORDER BY event_id",
                    (agent._last_event_id,),
                ).fetchall()

            for event_id, case_id, process_key, activity in rows:
                agent._last_event_id = max(agent._last_event_id, event_id)
                kind = agent._watch.get(activity)
                if kind is None:
                    continue  # не контрольная точка — не наша забота (ФТ-А-К-5)

                msg = Message(to=agent._recipient_jid)
                msg.set_metadata("performative", "inform")
                msg.set_metadata("notification_kind", kind)
                msg.body = f"{kind}: {process_key}/{case_id} — контрольная точка «{activity}»"
                await self.send(msg)
                agent.dispatched.append({"case_id": case_id, "kind": kind, "source_event_id": event_id})

                with psycopg.connect(agent._database_url) as conn2:
                    conn2.execute(
                        "INSERT INTO event_log (case_id, process_key, activity, lifecycle, resource, attributes) "
                        "VALUES (%s, %s, 'notification_dispatched', 'complete', 'controller', %s)",
                        (case_id, process_key, psycopg.types.json.Json({"kind": kind, "source_event_id": event_id})),
                    )
                    conn2.commit()

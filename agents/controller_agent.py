"""Агент Контролер (T-34, ФТ-А-К-1..5): следит за контрольными точками и
уведомляет о напоминаниях/эскалациях.

Сами таймеры и их срабатывание реализованы в BPMN-модели поверх оркестратора
(граничные события, спайк T-28, доказано на живом движке) — Контролер не
дублирует эту механику. Его задача уже, но именно та, что описана в
требованиях: превратить свершившийся факт "таймер сработал" в уведомление
конкретному получателю (FIPA inform) и лестницу эскалации, не выполняя при
этом никаких действий за исполнителя (ФТ-А-К-5).

watch_activities сопоставляет id BPMN-задачи со "смыслом" контрольной точки
(например, {"remind": "напоминание", "escalate": "эскалация"}). Подключение
новых контрольных точек, добавленных контуром адаптации (T-42), — это
расширение словаря в рантайме; сам механизм подписки не меняется.
"""
from __future__ import annotations

import psycopg
from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour
from spade.message import Message


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

    async def setup(self) -> None:
        with psycopg.connect(self._database_url) as conn:
            row = conn.execute("SELECT coalesce(max(event_id), 0) FROM event_log").fetchone()
            self._last_event_id = row[0]
        self.add_behaviour(self.Watch(period=self._tick_seconds))

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

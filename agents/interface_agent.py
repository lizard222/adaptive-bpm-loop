"""Агент Интерфейсный (T-37, ФТ-А-И-1..3): мост человек↔МАС.

Единственный мост, который реально нужен между REST-слоем (api/, T-37) и
многоагентной системой: предложения корректировок от Аналитик-Адаптера
(T-42, FIPA propose) требуют ОТВЕТА на конкретный thread от какого-то
постоянно работающего JID — раньше эту роль в смоук-тестах играли
одноразовые агенты-заглушки ("завкафедрой"). Интерфейсный агент — рабочая
версия той же роли, управляемая через REST, а не хардкод в тесте.

Задачи (ФТ-С-4) НЕ идут через этот мост: у READY-задачи в оркестраторе нет
"агента", ожидающего FIPA-ответа — REST-слой вызывает Orchestrator.
complete_task() напрямую (orchestrator/engine.py). Мост нужен только там,
где на другом конце реально ждут FIPA-сообщение с конкретным thread.

Устройство — та же схема "смотри в БД, реагируй на изменения", что и у
Контролера (agents/controller_agent.py), только сообщения идут в обе
стороны:
  - Listen (приём): получает FIPA propose от Аналитик-Адаптера, кладёт
    предложение в pending_decisions (thread, proposer_jid, ...). Дальше
    предложение видно через REST (GET /corrections/pending).
  - Dispatch (отправка): раз в tick_seconds проверяет pending_decisions на
    решённые, но ещё не отправленные (decided_at IS NOT NULL AND
    replied_at IS NULL) — решение принимается через REST
    (POST /corrections/{id}/decide), не этим агентом — и отправляет
    настоящий accept-proposal/reject-proposal обратно тому, кто предложил
    (proposer_jid), с тем же thread.
"""
from __future__ import annotations

import psycopg
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.message import Message


class InterfaceAgent(Agent):
    def __init__(self, jid: str, password: str, database_url: str, tick_seconds: float = 1.0):
        super().__init__(jid, password)
        self.database_url = database_url
        self.tick_seconds = tick_seconds
        self.received: list[dict] = []   # для наблюдения из тестов
        self.dispatched: list[dict] = []  # для наблюдения из тестов

    async def setup(self) -> None:
        self.add_behaviour(self.Listen())
        self.add_behaviour(self.Dispatch(period=self.tick_seconds))

    class Listen(CyclicBehaviour):
        async def run(self) -> None:
            msg = await self.receive(timeout=5)
            if msg is None or msg.get_metadata("performative") != "propose":
                return
            agent: InterfaceAgent = self.agent
            row = {
                "thread": msg.thread,
                "proposer_jid": str(msg.sender),
                "process_key": msg.get_metadata("process_key") or "",
                "kind": msg.get_metadata("kind") or "",
                "target": msg.get_metadata("target") or "",
                "justification": msg.body or "",
            }
            with psycopg.connect(agent.database_url) as conn:
                conn.execute(
                    "INSERT INTO pending_decisions "
                    "(thread, proposer_jid, process_key, kind, target, justification) "
                    "VALUES (%(thread)s, %(proposer_jid)s, %(process_key)s, %(kind)s, %(target)s, %(justification)s) "
                    "ON CONFLICT (thread) DO NOTHING",
                    row,
                )
                conn.commit()
            agent.received.append(row)

    class Dispatch(PeriodicBehaviour):
        async def run(self) -> None:
            agent: InterfaceAgent = self.agent
            with psycopg.connect(agent.database_url) as conn:
                rows = conn.execute(
                    "SELECT id, thread, proposer_jid, status FROM pending_decisions "
                    "WHERE decided_at IS NOT NULL AND replied_at IS NULL"
                ).fetchall()

            for decision_id, thread, proposer_jid, status in rows:
                reply = Message(to=proposer_jid)
                reply.thread = thread
                reply.set_metadata(
                    "performative", "accept-proposal" if status == "accepted" else "reject-proposal"
                )
                await self.send(reply)
                agent.dispatched.append({"id": decision_id, "thread": thread, "status": status})
                with psycopg.connect(agent.database_url) as conn2:
                    conn2.execute(
                        "UPDATE pending_decisions SET replied_at = now() WHERE id = %s", (decision_id,)
                    )
                    conn2.commit()

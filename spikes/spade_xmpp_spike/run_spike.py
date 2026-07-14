# -*- coding: utf-8 -*-
"""Спайк SPADE + Prosody: реально ли поднимается связь между двумя агентами
через локальный XMPP-сервер (docker-compose: abl-prosody, порт 5222).

Проверяет: авторегистрацию учётных записей (XEP-0077), отправку и получение
сообщения с метаданными FIPA ACL (performative), доставку в оба конца.
"""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))
from agents.xmpp_dev import enable_unencrypted_plain_auth  # noqa: E402

enable_unencrypted_plain_auth()

import spade  # noqa: E402
from spade.agent import Agent  # noqa: E402
from spade.behaviour import CyclicBehaviour, OneShotBehaviour  # noqa: E402
from spade.message import Message  # noqa: E402

DOMAIN = "localhost"
PASSWORD = "spike-password"
run_id = uuid.uuid4().hex[:6]
SENDER_JID = f"spike-sender-{run_id}@{DOMAIN}"
RECEIVER_JID = f"spike-receiver-{run_id}@{DOMAIN}"

received: list[dict] = []
checks: list[tuple[str, bool]] = []


def check(label: str, cond: bool) -> None:
    checks.append((label, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + label)


class ReceiverAgent(Agent):
    class Listen(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=8)
            if msg is not None:
                received.append({
                    "body": msg.body,
                    "performative": msg.get_metadata("performative"),
                    "sender": str(msg.sender),
                })

    async def setup(self):
        self.add_behaviour(self.Listen())


class SenderAgent(Agent):
    class SendOnce(OneShotBehaviour):
        async def run(self):
            msg = Message(to=RECEIVER_JID)
            msg.body = "запуск экземпляра demo_process на 2026-10-01"
            msg.set_metadata("performative", "inform")
            msg.set_metadata("protocol", "fipa-request-like")
            await self.send(msg)

    async def setup(self):
        self.add_behaviour(self.SendOnce())


async def main() -> int:
    receiver = ReceiverAgent(RECEIVER_JID, PASSWORD)
    await receiver.start(auto_register=True)
    check("receiver подключился и зарегистрировался на Prosody", receiver.is_alive())

    sender = SenderAgent(SENDER_JID, PASSWORD)
    await sender.start(auto_register=True)
    check("sender подключился и зарегистрировался на Prosody", sender.is_alive())

    await asyncio.sleep(3)

    check("сообщение доставлено получателю", len(received) == 1)
    if received:
        check("тело сообщения совпадает", "запуск экземпляра" in received[0]["body"])
        check("метаданные FIPA (performative=inform) сохранились", received[0]["performative"] == "inform")
        check("отправитель определён верно", received[0]["sender"].startswith(f"spike-sender-{run_id}"))

    await sender.stop()
    await receiver.stop()

    failed = [label for label, ok in checks if not ok]
    print(f"\nИтого: {len(checks) - len(failed)}/{len(checks)} проверок пройдено")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(spade.run(main()))

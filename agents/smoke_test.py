# -*- coding: utf-8 -*-
"""Сквозной смоук-тест Планировщик+Контролер (B3/B4, T-33/T-34) на реальной
инфраструктуре: PostgreSQL + Prosody.

Сценарий: Планировщик запускает экземпляр demo_process и тикает движок;
никто не выполняет review_request вручную -> срабатывает напоминание (2с),
затем эскалация (4с, отменяет задачу). Контролер обнаруживает оба события в
event_log и рассылает FIPA-уведомления получателю — реальному SPADE-агенту,
который их принимает и складывает в список (проверяем содержимое).

Запуск (нужен docker compose up): python -m agents.smoke_test
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from .xmpp_dev import enable_unencrypted_plain_auth

enable_unencrypted_plain_auth()

import spade  # noqa: E402
from spade.agent import Agent  # noqa: E402
from spade.behaviour import CyclicBehaviour  # noqa: E402

from api.config import settings  # noqa: E402
from .controller_agent import ControllerAgent  # noqa: E402
from .scheduler_agent import LaunchRule, SchedulerAgent  # noqa: E402

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "demo_process.bpmn"
RUN_ID = uuid.uuid4().hex[:6]
PASSWORD = "smoke-password"


class RecipientAgent(Agent):
    class Listen(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is not None:
                self.agent.inbox.append({
                    "kind": msg.get_metadata("notification_kind"),
                    "body": msg.body,
                })

    async def setup(self):
        self.inbox: list[dict] = []
        self.add_behaviour(self.Listen())


async def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    recipient_jid = f"smoke-recipient-{RUN_ID}@localhost"
    controller_jid = f"smoke-controller-{RUN_ID}@localhost"
    scheduler_jid = f"smoke-scheduler-{RUN_ID}@localhost"

    recipient = RecipientAgent(recipient_jid, PASSWORD)
    await recipient.start(auto_register=True)

    controller = ControllerAgent(
        controller_jid, PASSWORD, settings.database_url,
        watch_activities={"remind": "напоминание", "escalate": "эскалация"},
        recipient_jid=recipient_jid, tick_seconds=0.5,
    )
    await controller.start(auto_register=True)

    # process_key уникален для прогона: _is_due смотрит на последний старт ПО
    # ЭТОМУ КЛЮЧУ в общем event_log, а demo_process используется и другими
    # смоук-тестами (orchestrator, eventlog) — общий ключ дал бы ложное
    # "ещё не пора" из-за их недавних запусков.
    rule = LaunchRule(
        process_key=f"demo_process_{RUN_ID}", bpmn_file=BPMN, process_id="demo_process",
        interval_seconds=3600, param_version=7,
    )
    scheduler = SchedulerAgent(
        scheduler_jid, PASSWORD, settings.database_url, rules=[rule], tick_seconds=0.5,
    )
    await scheduler.start(auto_register=True)

    await asyncio.sleep(2)
    check("Планировщик запустил ровно один экземпляр", len(scheduler.launched_case_ids) == 1)
    case_id = scheduler.launched_case_ids[0] if scheduler.launched_case_ids else None

    await asyncio.sleep(3)  # напоминание (2с) должно долететь
    kinds_so_far = [m["kind"] for m in recipient.inbox]
    check("напоминание получено адресатом", "напоминание" in kinds_so_far)

    await asyncio.sleep(3)  # эскалация (4с) должна долететь
    kinds_final = [m["kind"] for m in recipient.inbox]
    check("эскалация получена адресатом", "эскалация" in kinds_final)
    check("оба уведомления — про один и тот же экземпляр",
          all(case_id in m["body"] for m in recipient.inbox) if case_id else False)
    check("Контролер зафиксировал обе отправки во внутреннем списке", len(controller.dispatched) == 2)

    final_state = scheduler.orchestrator.get_state(case_id) if case_id else {"completed": False}
    check("процесс завершился (по ветке эскалации)", final_state["completed"])

    await scheduler.stop()
    await controller.stop()
    await recipient.stop()

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    print("recipient.inbox:", recipient.inbox)
    print("controller.dispatched:", controller.dispatched)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(spade.run(main()))

# -*- coding: utf-8 -*-
"""Смоук-тест: реальная модель "Защита ВКР" (bpmn/demo/vkr_defense.bpmn,
mining.control_points.VKR_DEFENSE_CONTROL_POINTS) — первая модель,
сочетающая НЕСКОЛЬКО контрольных точек с ПАРАМЕТРИЗОВАННЫМИ таймерами (см.
комментарий в control_points.py). Структура теста — по образцу
agents/second_process_smoke_test.py (тот же приём: линейная цепочка с двумя
контрольными точками подряд, "воронка" — прерывающая эскалация на первой
точке не пускает часть экземпляров ко второй).

Запуск: python -m agents.vkr_defense_smoke_test
"""
from __future__ import annotations

import asyncio
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .xmpp_dev import enable_unencrypted_plain_auth

enable_unencrypted_plain_auth()

import psycopg  # noqa: E402
import spade  # noqa: E402
from spade.agent import Agent  # noqa: E402
from spade.behaviour import CyclicBehaviour  # noqa: E402
from spade.message import Message  # noqa: E402

from api.config import settings  # noqa: E402
from mining.control_points import VKR_DEFENSE_CONTROL_POINTS  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402
from simgen.executor import ExecutorProfile  # noqa: E402
from simgen.run import run_cycle  # noqa: E402

from .analyst_adapter_agent import AnalystAdapterAgent  # noqa: E402

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "vkr_defense.bpmn"
RUN_ID = uuid.uuid4().hex[:6]
PASSWORD = "smoke-password"


class DeptHeadStub(Agent):
    """Принимает предложение по approve_topics, отклоняет по normcontrol —
    решение по TARGET, как в second_process_smoke_test.py (у обеих
    корректировок kind, скорее всего, одинаковый — shift_start)."""

    class Decide(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None or msg.get_metadata("performative") != "propose":
                return
            target = msg.get_metadata("target")
            self.agent.seen.append(target)
            reply = Message(to=str(msg.sender))
            reply.thread = msg.thread
            reply.set_metadata(
                "performative", "accept-proposal" if target == "approve_topics" else "reject-proposal"
            )
            await self.send(reply)

    async def setup(self):
        self.seen: list[str] = []
        self.add_behaviour(self.Decide())


def _fetch_applied(process_key: str) -> list[tuple]:
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute(
            "SELECT version, kind, target FROM applied_corrections WHERE process_key=%s ORDER BY target",
            (process_key,),
        ).fetchall()


async def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    process_key = f"vkr_defense_{RUN_ID}"
    orch = Orchestrator(settings.database_url)

    # escalate_topics — ПРЕРЫВАЮЩЕЕ событие: экземпляр, эскалированный на
    # approve_topics, до normcontrol вообще не доходит ("воронка", тот же
    # эффект, что у calculate_load->distribute_load). Параметры подобраны по
    # аналогии со вторым процессом (60 экземпляров, no_show=0.6) — устойчиво
    # к seed, оставляет достаточно выживших для normcontrol.
    sim = run_cycle(
        orch, random.Random(7), ExecutorProfile(no_show_probability=0.6), process_key, BPMN,
        "vkr_defense", n_instances=60,
        cycle_start=datetime(2026, 9, 1, tzinfo=timezone.utc), max_days=30,
        reminder_activities=("remind_topics", "remind_normcontrol"),
        escalation_activities=("escalate_topics", "escalate_normcontrol"),
        initial_data={"reminder_days": 7, "escalation_days": 14},
    )
    print(sim)

    depthead_jid = f"smoke-depthead-vkr-{RUN_ID}@localhost"
    adapter_jid = f"smoke-adapter-vkr-{RUN_ID}@localhost"

    depthead = DeptHeadStub(depthead_jid, PASSWORD)
    await depthead.start(auto_register=True)
    adapter = AnalystAdapterAgent(
        adapter_jid, PASSWORD, settings.database_url,
        recipient_jid=depthead_jid, notify_jids=[], decision_timeout=8.0,
    )
    await adapter.start(auto_register=True)

    result = await adapter.process_cycle(process_key, BPMN, VKR_DEFENSE_CONTROL_POINTS, mode="propose")

    check("конвейер посчитал ОБЕ контрольные точки модели ВКР раздельно",
          set(result.report.control_points.keys()) == {"approve_topics", "normcontrol"})
    check("предложены корректировки по ОБЕИМ точкам (не схлопнулись в одну)",
          {c.target for c in result.proposed} == {"approve_topics", "normcontrol"})
    check("завкафедрой увидел оба предложения одновременно (два thread в работе разом)",
          set(depthead.seen) == {"approve_topics", "normcontrol"})
    check("принято только approve_topics", {c.target for c in result.accepted} == {"approve_topics"})
    check("normcontrol отклонён, не применён", {c.target for c in result.rejected} == {"normcontrol"})
    check("в БД применена ровно одна корректировка — approve_topics",
          _fetch_applied(process_key) == [(1, "shift_start", "approve_topics")])
    check("ответ на 'чужой'/отклонённый thread не спутан с принятым (нет двойной версии)",
          result.version == 1)

    await adapter.stop()
    await depthead.stop()

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(spade.run(main()))

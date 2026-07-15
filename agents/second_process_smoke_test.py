# -*- coding: utf-8 -*-
"""Смоук-тест B6/T-38: второй процесс подключается конфигурацией.

Ничего в orchestrator/, agents/scheduler_agent.py, agents/controller_agent.py,
agents/analyst_adapter_agent.py, mining/conveyor.py, mining/corrections.py не
менялось для этого теста — только новый BPMN-файл
(bpmn/demo/workload_planning_days.bpmn) и новая запись control-точек
(mining/control_points.WORKLOAD_CONTROL_POINTS). Это и есть проверка NFR-9.

Заодно закрывает реальный пробел в покрытии C3: там ни разу не проверялось,
как агент ведёт себя, когда НЕСКОЛЬКО корректировок ждут решения человека
ОДНОВРЕМЕННО (в demo_process_days всего одна контрольная точка — предложение
всегда было единственным). Здесь второй процесс с двумя последовательными
контрольными точками (calculate_load, distribute_load) при высоком no-show
даёт два предложения сразу — стаб "завкафедрой" принимает одно, отклоняет
другое ПО target, а не по kind (у обеих корректировок kind одинаковый,
shift_start) — проверяет, что параллельные propose/accept/reject по разным
thread не путаются друг с другом.

Запуск: python -m agents.second_process_smoke_test
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
from mining.control_points import WORKLOAD_CONTROL_POINTS  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402
from simgen.executor import ExecutorProfile  # noqa: E402
from simgen.run import run_cycle  # noqa: E402

from .analyst_adapter_agent import AnalystAdapterAgent  # noqa: E402

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "workload_planning_days.bpmn"
RUN_ID = uuid.uuid4().hex[:6]
PASSWORD = "smoke-password"


class DeptHeadStub(Agent):
    """Принимает предложение по calculate_load, отклоняет по distribute_load —
    решение по TARGET, а не по kind (у обеих корректировок kind одинаковый)."""

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
                "performative", "accept-proposal" if target == "calculate_load" else "reject-proposal"
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

    process_key = f"workload_planning_days_{RUN_ID}"
    orch = Orchestrator(settings.database_url)

    # escalate_calc — ПРЕРЫВАЮЩЕЕ событие: экземпляр, эскалированный на
    # calculate_load, до distribute_load вообще не доходит ("воронка").
    # Поэтому high no-show + маленькая выборка почти всегда даёт слишком мало
    # выживших для distribute_load, чтобы их эскалации перешли порог 15% от
    # ПОЛНОЙ выборки (n_cases считается по всем 20, а не по дошедшим до шага).
    # 60 экземпляров + no_show=0.6 дают ожидаемо ~24 выживших после воронки,
    # из них ~60% тоже эскалируют на distribute_load — с запасом выше порога
    # для обеих точек, устойчиво к конкретному seed.
    sim = run_cycle(
        orch, random.Random(7), ExecutorProfile(no_show_probability=0.6), process_key, BPMN,
        "workload_planning_days", n_instances=60,
        cycle_start=datetime(2026, 4, 1, tzinfo=timezone.utc), max_days=30,
        reminder_activities=("remind_calc", "remind_dist"),
        escalation_activities=("escalate_calc", "escalate_dist"),
    )
    print(sim)

    depthead_jid = f"smoke-depthead2-{RUN_ID}@localhost"
    adapter_jid = f"smoke-adapter2-{RUN_ID}@localhost"

    depthead = DeptHeadStub(depthead_jid, PASSWORD)
    await depthead.start(auto_register=True)
    adapter = AnalystAdapterAgent(
        adapter_jid, PASSWORD, settings.database_url,
        recipient_jid=depthead_jid, notify_jids=[], decision_timeout=8.0,
    )
    await adapter.start(auto_register=True)

    result = await adapter.process_cycle(process_key, BPMN, WORKLOAD_CONTROL_POINTS, mode="propose")

    check("конвейер посчитал ОБЕ контрольные точки процесса раздельно",
          set(result.report.control_points.keys()) == {"calculate_load", "distribute_load"})
    check("предложены корректировки по ОБЕИМ точкам (не схлопнулись в одну)",
          {c.target for c in result.proposed} == {"calculate_load", "distribute_load"})
    check("завкафедрой увидел оба предложения одновременно (два thread в работе разом)",
          set(depthead.seen) == {"calculate_load", "distribute_load"})
    check("принято только calculate_load", {c.target for c in result.accepted} == {"calculate_load"})
    check("distribute_load отклонён, не применён", {c.target for c in result.rejected} == {"distribute_load"})
    check("в БД применена ровно одна корректировка — calculate_load",
          _fetch_applied(process_key) == [(1, "shift_start", "calculate_load")])
    check("ответ на 'чужой'/отклонённый thread не спутан с принятым (нет двойной версии)",
          result.version == 1)

    await adapter.stop()
    await depthead.stop()

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(spade.run(main()))

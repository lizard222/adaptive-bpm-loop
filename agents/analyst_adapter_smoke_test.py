# -*- coding: utf-8 -*-
"""Сквозной смоук-тест агента Аналитик-Адаптер (C3/T-42) на реальной
инфраструктуре: PostgreSQL + Prosody.

Сценарии:
  1. propose-режим: высокий no-show -> корректировка shift_start; агент
     "завкафедрой" (стаб) принимает shift_start и отклоняет прочее — обе
     ветки решения проверяются по-настоящему через FIPA propose/accept-
     /reject-proposal, а не заглушкой "всегда согласен". Планировщик и
     Контролер (стабы-приёмники) должны получить уведомление о новой версии.
  2. auto-режим: корректировки применяются немедленно, без FIPA-диалога
     (имитационный эксперимент, ФТ-С-7.6).
  3. процесс без просрочек: ни одного предложения, ни одной применённой
     корректировки, ни одного уведомления — нет ложной активности агента.

Запуск: python -m agents.analyst_adapter_smoke_test
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
from mining.control_points import DEMO_CONTROL_POINTS  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402
from simgen.executor import ExecutorProfile  # noqa: E402
from simgen.run import run_cycle  # noqa: E402

from .analyst_adapter_agent import AnalystAdapterAgent  # noqa: E402

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "demo_process_days.bpmn"
RUN_ID = uuid.uuid4().hex[:6]
PASSWORD = "smoke-password"


class DeptHeadStub(Agent):
    """Принимает shift_start, отклоняет всё остальное — проверяет обе ветки решения."""

    class Decide(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None or msg.get_metadata("performative") != "propose":
                return
            self.agent.seen.append({"kind": msg.get_metadata("kind"), "target": msg.get_metadata("target")})
            reply = Message(to=str(msg.sender))
            reply.thread = msg.thread
            reply.set_metadata(
                "performative", "accept-proposal" if msg.get_metadata("kind") == "shift_start" else "reject-proposal"
            )
            await self.send(reply)

    async def setup(self):
        self.seen: list[dict] = []
        self.add_behaviour(self.Decide())


class NotifySink(Agent):
    class Listen(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is not None:
                self.agent.inbox.append(msg.body)

    async def setup(self):
        self.inbox: list[str] = []
        self.add_behaviour(self.Listen())


def _fetch_applied(process_key: str) -> list[tuple]:
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute(
            "SELECT version, kind, target, mode FROM applied_corrections WHERE process_key=%s ORDER BY id",
            (process_key,),
        ).fetchall()


def _fetch_reports_count(process_key: str) -> int:
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute(
            "SELECT count(*) FROM analysis_reports WHERE process_key=%s", (process_key,)
        ).fetchone()[0]


async def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    orch = Orchestrator(settings.database_url)

    depthead_jid = f"smoke-depthead-{RUN_ID}@localhost"
    scheduler_jid = f"smoke-sched-sink-{RUN_ID}@localhost"
    controller_jid = f"smoke-ctrl-sink-{RUN_ID}@localhost"
    adapter_jid = f"smoke-adapter-{RUN_ID}@localhost"

    depthead = DeptHeadStub(depthead_jid, PASSWORD)
    await depthead.start(auto_register=True)
    sched_sink = NotifySink(scheduler_jid, PASSWORD)
    await sched_sink.start(auto_register=True)
    ctrl_sink = NotifySink(controller_jid, PASSWORD)
    await ctrl_sink.start(auto_register=True)

    adapter = AnalystAdapterAgent(
        adapter_jid, PASSWORD, settings.database_url,
        recipient_jid=depthead_jid, notify_jids=[scheduler_jid, controller_jid],
        decision_timeout=8.0,
    )
    await adapter.start(auto_register=True)

    # --- Сценарий 1: propose-режим ---
    key_bad = f"demo_process_days_{RUN_ID}_bad"
    run_cycle(
        orch, random.Random(1), ExecutorProfile(no_show_probability=0.5), key_bad, BPMN, "demo_process_days",
        n_instances=20, cycle_start=datetime(2026, 10, 1, tzinfo=timezone.utc), max_days=30,
    )
    result1 = await adapter.process_cycle(key_bad, BPMN, DEMO_CONTROL_POINTS, mode="propose")

    check("сценарий 1: было предложено хотя бы одно решение (shift_start)",
          any(c.kind == "shift_start" for c in result1.proposed))
    check("сценарий 1: shift_start принят", any(c.kind == "shift_start" for c in result1.accepted))
    check("сценарий 1: завкафедрой реально видел предложение (FIPA propose дошёл)",
          any(s["kind"] == "shift_start" for s in depthead.seen))
    check("сценарий 1: версия применённых корректировок = 1 (первый цикл процесса)",
          result1.version == 1)
    check("сценарий 1: в БД реально записана применённая корректировка",
          _fetch_applied(key_bad) == [(1, "shift_start", "review_request", "propose")])
    check("сценарий 1: отчёт анализа сохранён (ФТ-А-А-5)", _fetch_reports_count(key_bad) == 1)

    await asyncio.sleep(1.5)
    check("сценарий 1: Планировщик получил уведомление о новой версии",
          any(f"v{result1.version}" in m for m in sched_sink.inbox))
    check("сценарий 1: Контролер получил уведомление о новой версии",
          any(f"v{result1.version}" in m for m in ctrl_sink.inbox))

    # --- Сценарий 2: auto-режим ---
    key_auto = f"demo_process_days_{RUN_ID}_auto"
    run_cycle(
        orch, random.Random(1), ExecutorProfile(no_show_probability=0.5), key_auto, BPMN, "demo_process_days",
        n_instances=20, cycle_start=datetime(2026, 10, 1, tzinfo=timezone.utc), max_days=30,
    )
    seen_before = len(depthead.seen)
    result2 = await adapter.process_cycle(key_auto, BPMN, DEMO_CONTROL_POINTS, mode="auto")

    check("сценарий 2 (auto): корректировка применена без FIPA-диалога с человеком",
          len(depthead.seen) == seen_before)
    check("сценарий 2 (auto): корректировка реально принята", len(result2.accepted) == len(result2.proposed) > 0)
    check("сценарий 2 (auto): версия тоже с единицы (независимая история по process_key)",
          result2.version == 1)
    check("сценарий 2 (auto): в БД зафиксирован режим 'auto'",
          all(row[3] == "auto" for row in _fetch_applied(key_auto)))

    # --- Сценарий 3: процесс без просрочек — агент не должен ничего предлагать ---
    key_good = f"demo_process_days_{RUN_ID}_good"
    run_cycle(
        orch, random.Random(2), ExecutorProfile(no_show_probability=0.0, delay_median_days=1.0), key_good, BPMN,
        "demo_process_days", n_instances=20, cycle_start=datetime(2026, 10, 1, tzinfo=timezone.utc), max_days=30,
    )
    seen_before_good = len(depthead.seen)
    result3 = await adapter.process_cycle(key_good, BPMN, DEMO_CONTROL_POINTS, mode="propose")

    check("сценарий 3: корректировок не предложено (нет ложных срабатываний)", result3.proposed == [])
    check("сценарий 3: версия не выставлялась (нечего применять)", result3.version is None)
    check("сценарий 3: завкафедрой не потревожен (не пришло ни одного propose)",
          len(depthead.seen) == seen_before_good)
    check("сценарий 3: отчёт анализа всё равно сохранён (даже пустой результат воспроизводим)",
          _fetch_reports_count(key_good) == 1)

    await adapter.stop()
    await depthead.stop()
    await sched_sink.stop()
    await ctrl_sink.stop()

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(spade.run(main()))

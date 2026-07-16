# -*- coding: utf-8 -*-
"""Сквозной смоук-тест E3 (часть T-25): контур адаптации в ЖИВОЙ системе, не
только в offline-эксперименте.

Два уровня проверки:
  1. Планировщик реально читает АКТУАЛЬНЫЕ параметры из process_params_current
     перед запуском — не встроенный дефолт правила. Проверяется предзаполнением
     таблицы перед стартом агента и сверкой initial_data запущенного экземпляра.
  2. Полный конвейер: Аналитик-Адаптер применяет корректировку (auto-режим) ->
     process_params_current обновлён -> И Планировщик, И Контролер реально
     получили FIPA-уведомление process_params_updated (раньше, до E3, это
     уведомление уходило в никуда — ни у одного агента не было ни одного
     receive-поведения).

Запуск: python -m agents.params_flow_smoke_test
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

from api.config import settings  # noqa: E402
from experiment.params import ProcessParams  # noqa: E402
from mining.control_points import EXPERIMENT_CONTROL_POINTS  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402
from simgen.executor import ExecutorProfile  # noqa: E402
from simgen.run import run_cycle  # noqa: E402

from .analyst_adapter_agent import AnalystAdapterAgent  # noqa: E402
from .controller_agent import ControllerAgent  # noqa: E402
from .params_store import get_current_params  # noqa: E402
from .scheduler_agent import LaunchRule, SchedulerAgent  # noqa: E402

BPMN = Path(__file__).parents[1] / "bpmn" / "demo" / "experiment_process.bpmn"
RUN_ID = uuid.uuid4().hex[:6]
PASSWORD = "smoke-password"
DEFAULT_PARAMS = ProcessParams(reminder_days=7, escalation_days=14)


def _instance_initial_data(process_key: str) -> dict | None:
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute(
            "SELECT attributes FROM event_log WHERE process_key=%s AND activity='process_instance' "
            "AND lifecycle='start' ORDER BY event_id DESC LIMIT 1",
            (process_key,),
        ).fetchone()
    return row[0].get("initial_data") if row else None


async def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    # --- Уровень 1: Планировщик читает актуальные параметры, не дефолт правила ---
    key_prefill = f"e3_prefill_{RUN_ID}"
    # Значение НАМЕРЕННО отличается от base_params правила (14) — проверяем,
    # что Планировщик реально читает это, а не игнорирует в пользу дефолта.
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            "INSERT INTO process_params_current (process_key, reminder_days, escalation_days, version) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (process_key) DO UPDATE "
            "SET reminder_days=EXCLUDED.reminder_days, escalation_days=EXCLUDED.escalation_days, version=EXCLUDED.version",
            (key_prefill, 7, 20, 1),  # escalation_days=20, НЕ 14 — отличается от base_params правила
        )
        conn.commit()

    scheduler_jid = f"smoke-sched3-{RUN_ID}@localhost"
    scheduler = SchedulerAgent(
        scheduler_jid, PASSWORD, settings.database_url,
        rules=[LaunchRule(key_prefill, BPMN, "experiment_process", interval_seconds=3600, base_params=DEFAULT_PARAMS)],
        tick_seconds=0.5,
    )
    await scheduler.start(auto_register=True)
    await asyncio.sleep(2)

    check("Планировщик запустил экземпляр", len(scheduler.launched_case_ids) == 1)
    initial_data = _instance_initial_data(key_prefill)
    check("initial_data экземпляра взят из БД (escalation_days=20), а не из base_params правила (14)",
          initial_data is not None and initial_data.get("escalation_days") == 20)

    # --- Уровень 2: полный конвейер уведомлений ---
    key_flow = f"e3_flow_{RUN_ID}"
    orch = Orchestrator(settings.database_url)
    run_cycle(
        orch, random.Random(3), ExecutorProfile(no_show_probability=0.5), key_flow, BPMN, "experiment_process",
        n_instances=20, cycle_start=datetime(2026, 10, 1, tzinfo=timezone.utc), max_days=30,
        initial_data=DEFAULT_PARAMS.as_initial_data(),
    )

    controller_jid = f"smoke-ctrl3-{RUN_ID}@localhost"
    controller = ControllerAgent(
        controller_jid, PASSWORD, settings.database_url,
        watch_activities={"remind": "напоминание", "escalate": "эскалация"},
        recipient_jid=f"smoke-sink3-{RUN_ID}@localhost", tick_seconds=0.5,
    )
    await controller.start(auto_register=True)

    adapter_jid = f"smoke-adapter3-{RUN_ID}@localhost"
    adapter = AnalystAdapterAgent(
        adapter_jid, PASSWORD, settings.database_url,
        recipient_jid=f"smoke-depthead3-{RUN_ID}@localhost",
        notify_jids=[scheduler_jid, controller_jid],
        default_params=DEFAULT_PARAMS,
    )
    await adapter.start(auto_register=True)

    result = await adapter.process_cycle(key_flow, BPMN, EXPERIMENT_CONTROL_POINTS, mode="auto")
    check("корректировка реально применена (auto-режим)", len(result.accepted) > 0)

    stored = get_current_params(settings.database_url, key_flow, DEFAULT_PARAMS)
    check("process_params_current обновлён для нового процесса",
          stored.escalation_days > DEFAULT_PARAMS.escalation_days or stored.reminder_days > DEFAULT_PARAMS.reminder_days)

    await asyncio.sleep(2)
    check("Планировщик получил FIPA-уведомление process_params_updated (раньше уходило в никуда)",
          any(n["process_key"] == key_flow for n in scheduler.received_notifications))
    check("Контролер получил FIPA-уведомление process_params_updated (раньше уходило в никуда)",
          any(n["process_key"] == key_flow for n in controller.received_notifications))

    await scheduler.stop()
    await controller.stop()
    await adapter.stop()

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(spade.run(main()))

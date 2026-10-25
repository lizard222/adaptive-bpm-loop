# -*- coding: utf-8 -*-
"""Смоук-тест: реальная модель "Защита ВКР" (bpmn/demo/vkr_defense.bpmn,
mining.control_points.VKR_DEFENSE_CONTROL_POINTS) — несколько контрольных
точек с ПАРАМЕТРИЗОВАННЫМИ таймерами и (E15) структурная адаптация.

Два цикла:
  1. Базовая модель. Синтетические исполнители опаздывают (норматив 2/6 дней
     при медиане задержки 3 дня): по всем трём контрольным точкам — доля
     напоминаний/эскалаций выше порога, а шаг без контроля «Отзыв
     руководителя» дольше нормы в большинстве экземпляров. Срок эскалации
     6 дней, а не меньше, — из-за «воронки»: прерывающие эскалации на трёх
     точках до отзыва при 2/4 днях оставляли до него 3 экземпляра из 60
     (меньше min_sample_size, корректировка честно не предлагалась).
     Аналитик-Адаптер предлагает 3 корректировки сроков + add_checkpoint на отзыв; «завкафедрой» принимает сдвиг по
     approve_topics и контрольную точку, остальное отклоняет. Итог: параметры
     v1 И модель v1 с контрольной точкой на отзыве; Контролер, получив
     уведомление, начинает следить за новой точкой.
  2. Новые экземпляры запускаются по модели v1 — на отзыве срабатывает
     напоминание; анализ видит отзыв как контрольную точку и не предлагает
     добавить её повторно. Экземпляры цикла 1 остались на базовой модели.

Процесс — копия vkr_defense в реестре под уникальным ключом (только в памяти
этого процесса): версии модели и параметры не задевают боевой vkr_defense.

Запуск: python -m agents.vkr_defense_smoke_test
"""
from __future__ import annotations

import asyncio
import dataclasses
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from .xmpp_dev import enable_unencrypted_plain_auth

enable_unencrypted_plain_auth()

import psycopg  # noqa: E402
import spade  # noqa: E402
from spade.agent import Agent  # noqa: E402
from spade.behaviour import CyclicBehaviour  # noqa: E402
from spade.message import Message  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from api.config import settings  # noqa: E402
from api.main import app  # noqa: E402
from experiment.params import ProcessParams  # noqa: E402
from mining.control_points import (  # noqa: E402
    VKR_DEFENSE_CONTROL_POINTS, VKR_DEFENSE_MONITORED_STEPS, added_control_point,
)
from orchestrator import Orchestrator  # noqa: E402
from orchestrator.process_registry import PROCESS_REGISTRY  # noqa: E402
from simgen.executor import ExecutorProfile  # noqa: E402
from simgen.run import run_cycle  # noqa: E402

from .analyst_adapter_agent import AnalystAdapterAgent  # noqa: E402
from .controller_agent import ControllerAgent  # noqa: E402
from .model_store import control_points_for, current_model_file, current_version, step_norm  # noqa: E402
from .params_store import get_current_params  # noqa: E402

RUN_ID = uuid.uuid4().hex[:6]
PASSWORD = "smoke-password"
REVIEW = "supervisor_review"
RELATIVE_POINTS = {"approve_topics", "publish_for_normcontrol", "normcontrol"}
CYCLE_1 = datetime(2026, 9, 1, tzinfo=timezone.utc)
CYCLE_2 = datetime(2026, 11, 15, tzinfo=timezone.utc)


class DeptHeadStub(Agent):
    """Принимает предложения по targets из self.accept, остальные отклоняет."""

    class Decide(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None or msg.get_metadata("performative") != "propose":
                return
            target = msg.get_metadata("target")
            self.agent.seen.append((msg.get_metadata("kind"), target))
            reply = Message(to=str(msg.sender))
            reply.thread = msg.thread
            reply.set_metadata(
                "performative", "accept-proposal" if target in self.agent.accept else "reject-proposal"
            )
            await self.send(reply)

    async def setup(self):
        self.seen: list[tuple[str, str]] = []
        self.accept: set[str] = set()
        self.add_behaviour(self.Decide())


def _fetch_applied(process_key: str) -> list[tuple]:
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute(
            "SELECT version, kind, target FROM applied_corrections WHERE process_key=%s ORDER BY version, target",
            (process_key,),
        ).fetchall()


def _cases_between(process_key: str, since: datetime, until: datetime | None = None) -> list[str]:
    """Экземпляры, начатые (первое событие) в [since, until)."""
    with psycopg.connect(settings.database_url) as conn:
        return [r[0] for r in conn.execute(
            "SELECT case_id FROM event_log WHERE process_key = %s GROUP BY case_id "
            "HAVING min(ts) >= %s AND (%s::timestamptz IS NULL OR min(ts) < %s)",
            (process_key, since, until, until),
        ).fetchall()]


def _count(process_key: str, case_ids: list[str], activity: str) -> int:
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute(
            "SELECT count(*) FROM event_log WHERE process_key = %s AND case_id = ANY(%s) "
            "AND activity = %s AND lifecycle = 'completed'",
            (process_key, case_ids, activity),
        ).fetchone()[0]


def _model_has(orch: Orchestrator, case_id: str, task_spec: str) -> bool:
    """Есть ли элемент в модели, сохранённой в состоянии экземпляра (не в
    дереве задач: у экземпляра, прерванного эскалацией раньше, до этого шага
    дерево не доходит)."""
    with psycopg.connect(settings.database_url) as conn:
        wf, _ = orch._load(conn, case_id)
    return task_spec in wf.spec.task_specs


async def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    process_key = f"vkr_defense_{RUN_ID}"
    db = settings.database_url
    # Нормативы процесса в этом тесте — 2/6 дней (симуляция и норма длительности
    # шага без контроля должны совпадать с параметрами процесса).
    params = ProcessParams(reminder_days=2, escalation_days=6)
    PROCESS_REGISTRY[process_key] = dataclasses.replace(
        PROCESS_REGISTRY["vkr_defense"], process_key=process_key, default_params=params,
    )
    orch = Orchestrator(db)
    reminders = ("remind_topics", "remind_publish", "remind_normcontrol", f"remind_{REVIEW}")
    escalations = ("escalate_topics", "escalate_publish", "escalate_normcontrol", f"escalate_{REVIEW}")

    # ---------- цикл 1: базовая модель ----------
    check("до адаптации модель базовая (v0)", current_version(db, process_key) == (0, ()))
    sim = run_cycle(
        orch, random.Random(7), ExecutorProfile(no_show_probability=0.05), process_key,
        current_model_file(db, process_key), "vkr_defense", n_instances=60,
        cycle_start=CYCLE_1, max_days=50, reminder_activities=reminders, escalation_activities=escalations,
        initial_data=params.as_initial_data(),
    )
    print(sim)
    cycle1_cases = _cases_between(process_key, CYCLE_1, CYCLE_2)

    depthead_jid = f"smoke-depthead-vkr-{RUN_ID}@localhost"
    adapter_jid = f"smoke-adapter-vkr-{RUN_ID}@localhost"
    controller_jid = f"smoke-controller-vkr-{RUN_ID}@localhost"

    depthead = DeptHeadStub(depthead_jid, PASSWORD)
    await depthead.start(auto_register=True)
    depthead.accept = {"approve_topics", REVIEW}
    controller = ControllerAgent(
        controller_jid, PASSWORD, db,
        watch_activities={a: "напоминание" for a in reminders[:3]} | {a: "эскалация" for a in escalations[:3]},
        recipient_jid=depthead_jid,
    )
    await controller.start(auto_register=True)
    adapter = AnalystAdapterAgent(
        adapter_jid, PASSWORD, db, recipient_jid=depthead_jid, notify_jids=[controller_jid],
        decision_timeout=8.0, default_params=params,
    )
    await adapter.start(auto_register=True)

    result = await adapter.process_cycle(
        process_key, current_model_file(db, process_key), control_points_for(db, process_key, VKR_DEFENSE_CONTROL_POINTS),
        mode="propose", monitored_steps=VKR_DEFENSE_MONITORED_STEPS, norm=step_norm(db, process_key),
    )
    review_stats = result.report.monitored_steps.get(REVIEW)
    print(f"  {review_stats}")

    check("конвейер посчитал все три контрольные точки раздельно",
          set(result.report.control_points.keys()) == RELATIVE_POINTS)
    check("конвейер измерил длительность шага без контроля (отзыв)",
          review_stats is not None and review_stats.n_cases >= 5)
    check("предложены корректировки сроков по всем трём точкам",
          {c.target for c in result.proposed if c.kind != "add_checkpoint"} == RELATIVE_POINTS)
    check("предложена контрольная точка на затянутый шаг без контроля",
          ("add_checkpoint", REVIEW) in {(c.kind, c.target) for c in result.proposed})
    check("завкафедрой увидел все четыре предложения", {t for _, t in depthead.seen} == RELATIVE_POINTS | {REVIEW})
    check("принято: сдвиг approve_topics и контрольная точка на отзыве",
          {(c.kind, c.target) for c in result.accepted} == {("shift_start", "approve_topics"), ("add_checkpoint", REVIEW)})
    check("в журнале корректировок — обе принятые, версия параметров 1",
          set(_fetch_applied(process_key)) == {(1, "add_checkpoint", REVIEW), (1, "shift_start", "approve_topics")})
    check("структурная адаптация: модель v1 с контрольной точкой на отзыве",
          result.model_version == 1 and result.added_checkpoints == (REVIEW,)
          and current_version(db, process_key) == (1, (REVIEW,)))
    model_v1 = current_model_file(db, process_key)
    check("новые экземпляры будут запускаться по файлу модели v1",
          model_v1.name == f"{process_key}.v1.bpmn" and f"remind_{REVIEW}_timer" in model_v1.read_text(encoding="utf-8"))

    added = added_control_point(REVIEW)
    for _ in range(20):  # уведомление Контролеру асинхронное
        if added.reminder_activity in controller.watched_activities:
            break
        await asyncio.sleep(0.5)
    check("Контролер получил уведомление о новой версии модели и следит за новой точкой",
          controller.watched_activities.get(added.reminder_activity) == "напоминание"
          and controller.watched_activities.get(added.escalation_activity) == "эскалация")
    await controller.stop()  # дальше — симуляция под управляемым временем, рассылка не нужна

    # Ручной запуск из UI (REST) тоже идёт по последней версии модели
    client = TestClient(app)
    token = client.post("/auth/token", data={"username": "secretary", "password": "secretary"}).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    launched = client.post(f"/processes/{process_key}/launch", json={}, headers=auth).json()["case_id"]
    check("запуск через UI/REST — по модели v1", _model_has(orch, launched, f"remind_{REVIEW}_timer"))
    summary = next(p for p in client.get("/dashboard/summary", headers=auth).json()["processes"]
                   if p["process_key"] == process_key)
    check("на обзоре видна версия модели и добавленная точка",
          summary["model"]["version"] == 1 and summary["model"]["added_checkpoints"] == [REVIEW])

    # ---------- цикл 2: модель v1 ----------
    current = get_current_params(db, process_key, params)
    run_cycle(
        orch, random.Random(11), ExecutorProfile(no_show_probability=0.05), process_key,
        current_model_file(db, process_key), "vkr_defense", n_instances=30,
        cycle_start=CYCLE_2, max_days=50, reminder_activities=reminders, escalation_activities=escalations,
        initial_data=current.as_initial_data(),
    )
    cycle2_cases = _cases_between(process_key, CYCLE_2)
    check("во втором цикле по отзыву срабатывает напоминание (таймер модели v1)",
          _count(process_key, cycle2_cases, added.reminder_activity) > 0)
    check("экземпляры первого цикла остались на базовой модели, второго — на v1",
          len(cycle1_cases) == 60 and len(cycle2_cases) == 30
          and not any(_model_has(orch, c, f"remind_{REVIEW}_timer") for c in cycle1_cases)
          and all(_model_has(orch, c, f"remind_{REVIEW}_timer") for c in cycle2_cases))

    depthead.accept = set()
    result2 = await adapter.process_cycle(
        process_key, current_model_file(db, process_key), control_points_for(db, process_key, VKR_DEFENSE_CONTROL_POINTS),
        case_ids=cycle2_cases, mode="propose",
        monitored_steps=VKR_DEFENSE_MONITORED_STEPS, norm=step_norm(db, process_key),
    )
    check("анализ второго цикла видит отзыв как контрольную точку",
          REVIEW in result2.report.control_points and REVIEW not in result2.report.monitored_steps)
    check("контрольную точку на отзыве повторно не предлагают",
          ("add_checkpoint", REVIEW) not in {(c.kind, c.target) for c in result2.proposed})
    check("без принятых add_checkpoint модель не меняется", current_version(db, process_key) == (1, (REVIEW,)))

    await adapter.stop()
    await depthead.stop()

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(spade.run(main()))

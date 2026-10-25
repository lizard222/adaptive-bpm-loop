# -*- coding: utf-8 -*-
"""Смоук-тест: ключевые даты защиты — предзащита и защита (E14, api/milestones.py).

Проверяет:
  * разбор и проверку дат (часовой пояс обязателен, неизвестные даты, порядок);
  * запуск с датами: даты в таблице, событие в журнале, плановые даты этапов
    у студента, «Назначена дата …» в ленте;
  * сроки шагов от даты: у предзащиты срок = дата + 1 день, напоминание — за
    день; у публикации финальных версий — за 10 дней до защиты;
  * перенос даты переносит взведённые таймеры; перенос в прошлое — таймер
    срабатывает сразу, эскалация необрывающая (шаг продолжается);
  * относительные контрольные точки контура адаптации не задеты;
  * без дат у шагов со сроком от даты срока нет;
  * доступ: менять даты — секретарь/завкафедрой/admin, студент и руководитель — 403.

Процесс — копия vkr_defense из реестра под уникальным на прогон ключом (только
в памяти этого процесса): экземпляры не попадают в статистику vkr_defense и
не тикаются фоновым циклом uvicorn.

Запуск: python -m api.milestones_smoke_test
"""
from __future__ import annotations

import dataclasses
import sys
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi.testclient import TestClient

from api.config import settings
from api.main import app
from api.milestones import MilestoneError, parse, timer_fields
from orchestrator import Orchestrator
from orchestrator.process_registry import PROCESS_REGISTRY

RUN_ID = uuid.uuid4().hex[:6]
KEY = f"vkr_defense_ms_{RUN_ID}"
ROLES = ("admin", "secretary", "supervisor", "normcontrol", "dept_head", "student")
DAY = timedelta(days=1)


def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    def raises(fn) -> bool:
        try:
            fn()
        except MilestoneError:
            return True
        return False

    # --- разбор и вычисление -------------------------------------------------
    check("дата без часового пояса отклоняется", raises(lambda: parse({"defense_at": "2027-06-20T09:00:00"})))
    check("неизвестная дата отклоняется", raises(lambda: parse({"gek_at": "2027-06-20T09:00:00+03:00"})))
    check("не дата отклоняется", raises(lambda: parse({"defense_at": "двадцатое июня"})))
    check("пустое значение пропускается", parse({"defense_at": "", "predefense_at": None}) == {})
    d = datetime(2027, 6, 20, 9, tzinfo=timezone.utc)
    f = timer_fields({"defense_at": d}, DAY)
    check("финальные версии: срок за 10 дней до защиты, напоминание за 12",
          f["publish_final_due_at"] == (d - 10 * DAY).isoformat()
          and f["publish_final_remind_at"] == (d - 12 * DAY).isoformat())
    check("без даты предзащиты её таймеры не вычисляются", "report_2_due_at" not in f)

    # --- запуск с датами -------------------------------------------------------
    PROCESS_REGISTRY[KEY] = dataclasses.replace(PROCESS_REGISTRY["vkr_defense"], process_key=KEY)
    client = TestClient(app)

    def headers(role: str) -> dict:
        token = client.post("/auth/token", data={"username": role, "password": role}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    h = {role: headers(role) for role in ROLES}
    orch = Orchestrator(settings.database_url)

    def n_instances() -> int:
        with psycopg.connect(settings.database_url) as conn:
            return conn.execute("SELECT count(*) FROM process_instances WHERE process_key = %s", (KEY,)).fetchone()[0]

    def complete(role: str, task: str, cid: str) -> int:
        return client.post(f"/tasks/{cid}/{task}/complete", json={}, headers=h[role]).status_code

    def task_row(cid: str, name: str) -> dict | None:
        return next((t for t in client.get("/tasks", headers=h["admin"]).json()["tasks"]
                     if t["case_id"] == cid and t["task_name"] == name), None)

    def put(role: str, cid: str, body: dict):
        return client.put(f"/cases/{cid}/milestones", json=body, headers=h[role])

    def my_view(cid: str) -> dict:
        return next(d for d in client.get("/me/defense", headers=h["student"]).json()["defenses"] if d["case_id"] == cid)

    def events(cid: str, activity: str) -> list:
        with psycopg.connect(settings.database_url) as conn:
            return conn.execute(
                "SELECT lifecycle, attributes FROM event_log WHERE case_id = %s AND activity = %s ORDER BY event_id",
                (cid, activity),
            ).fetchall()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    predefense, defense = now + 30 * DAY, now + 60 * DAY
    dates = {"predefense_at": predefense.isoformat(), "defense_at": defense.isoformat()}

    bad = client.post(f"/processes/{KEY}/launch", headers=h["secretary"],
                      json={"student": "student", "milestones": {"predefense_at": dates["defense_at"],
                                                                 "defense_at": dates["predefense_at"]}})
    check("запуск с предзащитой позже защиты -> 422, экземпляр не создан", bad.status_code == 422 and n_instances() == 0)

    r = client.post(f"/processes/{KEY}/launch", headers=h["secretary"], json={"student": "student", "milestones": dates})
    cid = r.json().get("case_id")
    check("запуск с датами -> 200, даты в ответе", r.status_code == 200
          and r.json()["milestones"]["defense_at"] == defense.isoformat())
    ev = events(cid, "milestones_set")
    check("в журнале — назначение обеих дат (прежних значений нет)",
          len(ev) == 1 and set(ev[0][1]["changes"]) == {"predefense_at", "defense_at"}
          and all(c["from"] is None for c in ev[0][1]["changes"].values()))

    view = my_view(cid)
    stages = {s["step"]: s for s in view["stages"]}
    check("студент видит обе даты", view["milestones"] == dates)
    check("плановая дата предзащиты — сама дата",
          stages["report_2"]["planned_at"] == predefense.isoformat() and stages["report_2"]["planned_rule"] == "дата предзащиты")
    check("публикация для нормоконтроля — за 14 дней до защиты",
          stages["publish_for_normcontrol"]["planned_at"] == (defense - 14 * DAY).isoformat()
          and stages["publish_for_normcontrol"]["planned_rule"] == "за 14 дн. до защиты")
    check("у этапов без привязки к дате плановой даты нет", stages["normcontrol"]["planned_at"] is None)
    check("в ленте «Назначена дата защиты» с самой датой",
          any(i["text"] == "Назначена дата защиты" and i["at"] == defense.isoformat() for i in view["feed"]))

    view_staff = client.get(f"/cases/{cid}/milestones", headers=h["supervisor"]).json()
    check("сотрудник видит даты и плановые даты этапов",
          view_staff["milestones"] == dates and "publish_final" in view_staff["planned"])
    check("студенту служебный GET дат закрыт -> 403",
          client.get(f"/cases/{cid}/milestones", headers=h["student"]).status_code == 403)

    # --- сроки предзащиты от даты -------------------------------------------------
    complete("secretary", "approve_topics", cid)
    row = task_row(cid, "report_2")
    check("срок предзащиты — день после даты, напоминание — накануне",
          row["due_at"] == (predefense + DAY).isoformat() and row["remind_at"] == (predefense - DAY).isoformat())

    # --- права и проверка ввода -------------------------------------------------
    check("студент не может менять даты -> 403", put("student", cid, dates).status_code == 403)
    check("руководитель ВКР не может менять даты -> 403", put("supervisor", cid, dates).status_code == 403)
    check("предзащита позже защиты -> 422",
          put("secretary", cid, {"predefense_at": (defense + DAY).isoformat()}).status_code == 422)
    check("дата без пояса -> 422", put("secretary", cid, {"defense_at": "2027-06-20T09:00:00"}).status_code == 422)
    check("неизвестный экземпляр -> 404", put("secretary", f"nope_{RUN_ID}", dates).status_code == 404)
    check("та же дата повторно — нового события нет",
          put("secretary", cid, dates).status_code == 200 and len(events(cid, "milestones_set")) == 1)

    # --- перенос в прошлое: таймеры срабатывают, шаг продолжается ----------------
    moved = now - 2 * DAY
    r = put("dept_head", cid, {"predefense_at": moved.isoformat()})
    check("завкафедрой переносит предзащиту -> 200", r.status_code == 200
          and r.json()["milestones"]["predefense_at"] == moved.isoformat())
    check("напоминание и эскалация по предзащите сработали сразу",
          len(events(cid, "remind_report_2")) == 1 and len(events(cid, "escalate_report_2")) == 1)
    row = task_row(cid, "report_2")
    check("эскалация необрывающая: предзащита по-прежнему ждёт отметки", row is not None)
    check("срок предзащиты теперь истёк", row["urgency"] == "critical" and row["due_at"] == (moved + DAY).isoformat())
    texts = [i["text"] for i in my_view(cid)["feed"]]
    check("студент видит перенос и истёкший срок",
          "Перенесена дата предзащиты" in texts and any(t.startswith("Срок этапа «Предзащита» истёк") for t in texts))

    # --- относительные контрольные точки не задеты ---------------------------------
    complete("supervisor", "report_2", cid)
    row = task_row(cid, "publish_for_normcontrol")
    check("у публикации для нормоконтроля срок по-прежнему относительный — 14 дней от начала шага",
          abs(datetime.fromisoformat(row["due_at"]) - datetime.now(timezone.utc) - 14 * DAY) < timedelta(minutes=5))
    complete("student", "publish_for_normcontrol", cid)
    complete("normcontrol", "normcontrol", cid)
    row = task_row(cid, "publish_final")
    check("финальные версии: срок за 10 дней до защиты", row["due_at"] == (defense - 10 * DAY).isoformat())

    later = defense + 7 * DAY
    put("secretary", cid, {"defense_at": later.isoformat()})
    row = task_row(cid, "publish_final")
    check("перенос защиты сдвинул срок уже идущего шага", row["due_at"] == (later - 10 * DAY).isoformat())
    complete("student", "publish_final", cid)
    complete("supervisor", "supervisor_review", cid)
    row = task_row(cid, "admission_order")
    check("приказ о допуске: срок за 14 дней до защиты", row["due_at"] == (later - 14 * DAY).isoformat())
    complete("secretary", "admission_order", cid)
    row = task_row(cid, "defense")
    check("защита: срок — на следующий день после даты", row["due_at"] == (later + DAY).isoformat())
    complete("secretary", "defense", cid)
    check("завершённому экземпляру даты не меняют -> 422",
          put("secretary", cid, {"defense_at": now.isoformat()}).status_code == 422)

    # --- без дат --------------------------------------------------------------------
    plain = f"ms_plain_{RUN_ID}"
    reg = PROCESS_REGISTRY[KEY]
    orch.start_instance(plain, KEY, reg.bpmn_file, reg.process_id, initial_data=reg.default_params.as_initial_data())
    orch.complete_task(plain, "approve_topics")
    row = task_row(plain, "report_2")
    check("без даты предзащиты у шага срока нет (таймер «не назначен» не показывается)",
          row["due_at"] is None and row["urgency"] is None)
    other = f"ms_other_{RUN_ID}"
    exp = PROCESS_REGISTRY["vkr_defense"]
    orch.start_instance(other, f"no_dates_{RUN_ID}", exp.bpmn_file, exp.process_id,
                        initial_data=exp.default_params.as_initial_data())
    check("процессу вне реестра даты не назначить -> 422", put("secretary", other, dates).status_code == 422)

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

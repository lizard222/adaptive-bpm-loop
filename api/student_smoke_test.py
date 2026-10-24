# -*- coding: utf-8 -*-
"""Смоук-тест: студент как участник процесса «Защита ВКР» (E13).

Проверяет:
  * подсказки api/student_guide.py идут ровно в порядке исполнения шагов
    модели bpmn/demo/vkr_defense.bpmn (список не разошёлся с моделью) и
    покрывают все шаги быстрой тестовой модели;
  * GET /me/defense показывает студенту только ЕГО защиты, с этапами
    («вы здесь», пройден, впереди, не пройден), сроком текущего этапа из
    таймеров движка, отметкой «ваш шаг» и лентой уведомлений из event_log;
  * эскалация (экземпляр стартует «в прошлом» под freezegun и доходит до
    таймера) видна студенту как напоминание + истёкший срок, этапы — «не пройден»;
  * доступ: сотрудники не открывают /me/defense, студент — обзор, документы,
    экземпляры процессов; запуск с «студентом», который не студент, -> 422.

process_key уникален на прогон — экземпляры не попадают в статистику
vkr_defense и не тикаются фоновым циклом uvicorn (он тикает только ключи реестра).

Запуск: python -m api.student_smoke_test
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi.testclient import TestClient
from freezegun import freeze_time

from api.config import settings
from api.main import app
from api.participants import STUDENT, bind
from api.student_guide import GUIDE
from api.task_access import resolve_lane
from orchestrator import Orchestrator
from orchestrator.process_registry import PROCESS_REGISTRY

RUN_ID = uuid.uuid4().hex[:6]
GUIDE_TITLES = {g["step"]: g["title"] for g in GUIDE}
ROLES = ("admin", "secretary", "supervisor", "dept_head", "student")


def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    client = TestClient(app)

    def headers(role: str) -> dict:
        token = client.post("/auth/token", data={"username": role, "password": role}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    h = {role: headers(role) for role in ROLES}
    reg = PROCESS_REGISTRY["vkr_defense"]
    orch = Orchestrator(settings.database_url)
    process_key = f"vkr_defense_student_{RUN_ID}"

    def start(case_id: str, student: str) -> None:
        orch.start_instance(case_id, process_key, reg.bpmn_file, reg.process_id,
                            initial_data=reg.default_params.as_initial_data())
        with psycopg.connect(settings.database_url) as conn:
            bind(conn, case_id, STUDENT, student)
            conn.commit()

    def ready(case_id: str) -> list[str]:
        return [t["name"] for t in orch.get_state(case_id)["tasks"] if t["state"] == "READY"]

    def complete(role: str, case_id: str, task_name: str) -> int:
        return client.post(f"/tasks/{case_id}/{task_name}/complete", json={}, headers=h[role]).status_code

    def my_view(case_id: str) -> dict | None:
        defenses = client.get("/me/defense", headers=h["student"]).json()["defenses"]
        return next((d for d in defenses if d["case_id"] == case_id), None)

    # --- подсказки = модель ---------------------------------------------------
    order_case = f"student_order_{RUN_ID}"
    start(order_case, f"order_student_{RUN_ID}")
    walked = []
    while (names := ready(order_case)) and len(walked) < 20:
        walked.append(names[0])
        orch.complete_task(order_case, names[0])
    check("порядок подсказок = порядок шагов модели vkr_defense",
          walked == [g["step"] for g in GUIDE])
    check("у каждого шага подсказки есть дорожка и в быстрой тестовой модели",
          all(resolve_lane("vkr_defense_fast", g["step"]) for g in GUIDE))
    check("у каждого этапа есть что сделать и источник в каталоге",
          all(g["what_to_do"] and g["source"] and g["catalog_due"] for g in GUIDE))

    # --- «Моя защита»: своё видно, чужое нет -------------------------------------
    mine = f"student_mine_{RUN_ID}"
    other = f"student_other_{RUN_ID}"
    start(mine, "student")
    start(other, f"other_student_{RUN_ID}")

    view = my_view(mine)
    check("студент видит свою защиту", view is not None)
    check("чужую защиту студент не видит", my_view(other) is None)
    check("защита шага проверки порядка (другой студент) тоже не видна", my_view(order_case) is None)
    stages = {s["step"]: s for s in view["stages"]}
    check("7 этапов, текущий — утверждение темы",
          len(view["stages"]) == 7 and view["current"] == "approve_topics"
          and stages["approve_topics"]["status"] == "current"
          and all(s["status"] == "upcoming" for s in view["stages"][1:]))
    check("у текущего этапа срок из таймера и отметка «в срок»",
          stages["approve_topics"]["due_at"] is not None and stages["approve_topics"]["urgency"] == "good")
    check("у будущих этапов срока нет (он появится, когда этап начнётся)",
          stages["normcontrol"]["due_at"] is None)
    check("«ваш шаг» — ровно на двух публикациях в Moodle",
          {s["step"] for s in view["stages"] if s["is_mine"]} == {"publish_for_normcontrol", "publish_final"})
    check("в ленте — запуск процесса", any(f["text"] == "Запущен процесс защиты ВКР" for f in view["feed"]))

    complete("secretary", mine, "approve_topics")
    complete("supervisor", mine, "report_2")
    view = my_view(mine)
    stages = {s["step"]: s for s in view["stages"]}
    check("после двух шагов студент на своём этапе",
          view["current"] == "publish_for_normcontrol" and stages["publish_for_normcontrol"]["is_mine"]
          and stages["approve_topics"]["status"] == "done" and stages["report_2"]["status"] == "done")
    check("срок своего этапа из таймеров — через 14 дней",
          abs(datetime.fromisoformat(stages["publish_for_normcontrol"]["due_at"])
              - datetime.now(timezone.utc) - timedelta(days=14)) < timedelta(minutes=5))
    check("студент выполняет свой этап -> 200", complete("student", mine, "publish_for_normcontrol") == 200)
    view = my_view(mine)
    check("в ленте — «выполнен (вами)»",
          f"Этап «{GUIDE_TITLES['publish_for_normcontrol']}» выполнен (вами)" in [f["text"] for f in view["feed"]])
    check("этапы сотрудников в ленте — без «(вами)»",
          any(f["text"].startswith("Этап «Предзащита» выполнен") and "(вами)" not in f["text"] for f in view["feed"]))
    check("каждое выполнение — одна запись в ленте (не дубль complete/completed)",
          sum("Предзащита" in f["text"] for f in view["feed"]) == 1)

    # --- эскалация глазами студента ---------------------------------------------
    late = f"student_late_{RUN_ID}"
    with freeze_time(datetime.now(timezone.utc) - timedelta(days=20)):
        start(late, "student")
    orch.tick(late)
    view = my_view(late)
    stages = {s["step"]: s for s in view["stages"]}
    texts = [f["text"] for f in view["feed"]]
    check("просроченная защита завершена эскалацией", view["status"] == "completed" and view["current"] is None)
    check("в ленте — напоминание о сроке", any(t.startswith("Напоминание: подходит срок этапа «Утверждение темы") for t in texts))
    check("в ленте — истёкший срок и уведомление завкафедрой",
          any(t.startswith("Срок этапа «Утверждение темы") and "заведующий" in t for t in texts))
    check("все этапы — «не пройден»", all(s["status"] == "skipped" for s in view["stages"]))

    # --- доступ ----------------------------------------------------------------
    check("секретарь не открывает /me/defense -> 403",
          client.get("/me/defense", headers=h["secretary"]).status_code == 403)
    check("завкафедрой не открывает /me/defense -> 403",
          client.get("/me/defense", headers=h["dept_head"]).status_code == 403)
    check("студент не открывает обзор -> 403",
          client.get("/dashboard/summary", headers=h["student"]).status_code == 403)
    check("студент не открывает документы -> 403",
          client.get("/documents", headers=h["student"]).status_code == 403)
    check("студент не открывает список экземпляров -> 403",
          client.get("/processes/vkr_defense/instances", headers=h["student"]).status_code == 403)
    check("студент не может запустить процесс -> 403",
          client.post("/processes/vkr_defense/launch", json={}, headers=h["student"]).status_code == 403)
    check("запуск с «студентом», который не студент -> 422 (экземпляр не создаётся)",
          client.post("/processes/vkr_defense/launch", json={"student": "secretary"},
                      headers=h["secretary"]).status_code == 422)

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

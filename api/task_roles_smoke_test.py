# -*- coding: utf-8 -*-
"""Смоук-тест: роли на сервере по дорожкам BPMN (api/task_access.py).

Прогоняет экземпляр модели "Защита ВКР" (bpmn/demo/vkr_defense.bpmn, 7 шагов,
дорожки "Секретарь кафедры"/"Руководитель ВКР"/"Студент"/"Нормоконтролёр")
через REST под разными ролями: каждый видит и выполняет только шаги своей
дорожки, чужой шаг -> 403, admin видит всё. Шаги дорожки "Студент" — только
студенту, привязанному к этой защите (api/participants.py): второй экземпляр
привязан к другому студенту, и его шаг демо-студенту не виден и не доступен.

process_key уникален на прогон (как в остальных смоук-тестах) — тестовые
экземпляры не попадают в "боевую" статистику vkr_defense, а дорожки при этом
берутся из сериализованной модели экземпляра (путь для процессов вне
реестра); путь "дорожка из модели реестра" проверяется отдельно, без БД.

Запуск: python -m api.task_roles_smoke_test
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi.testclient import TestClient

from api.config import settings
from api.main import app
from api.participants import STUDENT, bind
from api.task_access import resolve_lane
from orchestrator import Orchestrator
from orchestrator.process_registry import PROCESS_REGISTRY

RUN_ID = uuid.uuid4().hex[:6]
ROLES = ("admin", "secretary", "normcontrol", "supervisor", "dept_head", "student")


def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    check("дорожка из модели реестра: approve_topics -> Секретарь кафедры",
          resolve_lane("vkr_defense", "approve_topics") == "Секретарь кафедры")
    check("дорожка из модели реестра: normcontrol -> Нормоконтролёр",
          resolve_lane("vkr_defense", "normcontrol") == "Нормоконтролёр")
    check("дорожка из модели реестра: publish_for_normcontrol -> Студент",
          resolve_lane("vkr_defense", "publish_for_normcontrol") == "Студент")
    check("процесс вне реестра без сохранённой дорожки -> нет дорожки",
          resolve_lane(f"nope_{RUN_ID}", "approve_topics", None) is None)

    client = TestClient(app)

    def headers(role: str) -> dict:
        token = client.post("/auth/token", data={"username": role, "password": role}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    h = {role: headers(role) for role in ROLES}

    def visible(role: str, cid: str | None = None) -> list[str]:
        cid = cid or case_id
        return [t["task_name"] for t in client.get("/tasks", headers=h[role]).json()["tasks"] if t["case_id"] == cid]

    def complete(role: str, task_name: str, cid: str | None = None) -> int:
        cid = cid or case_id
        return client.post(f"/tasks/{cid}/{task_name}/complete", json={}, headers=h[role]).status_code

    def task_row(role: str, name: str) -> dict:
        return next(t for t in client.get("/tasks", headers=h[role]).json()["tasks"]
                    if t["case_id"] == case_id and t["task_name"] == name)

    reg = PROCESS_REGISTRY["vkr_defense"]
    orch = Orchestrator(settings.database_url)
    case_id = f"roles_{RUN_ID}"
    other_case = f"roles_other_{RUN_ID}"
    for cid, student in ((case_id, "student"), (other_case, f"other_student_{RUN_ID}")):
        orch.start_instance(cid, f"vkr_defense_roles_{RUN_ID}", reg.bpmn_file, reg.process_id,
                            initial_data=reg.default_params.as_initial_data())
        with psycopg.connect(settings.database_url) as conn:
            bind(conn, cid, STUDENT, student)
            conn.commit()

    check("секретарь видит approve_topics", visible("secretary") == ["approve_topics"])
    check("нормоконтролёр НЕ видит approve_topics", visible("normcontrol") == [])
    check("руководитель ВКР пока ничего не видит (предзащита ещё не наступила)", visible("supervisor") == [])
    check("завкафедрой не видит шагов процесса (его работа — корректировки)", visible("dept_head") == [])
    check("admin видит всё", visible("admin") == ["approve_topics"])
    lanes = [t.get("lane") for t in client.get("/tasks", headers=h["admin"]).json()["tasks"] if t["case_id"] == case_id]
    check("в ответе /tasks есть дорожка шага", lanes == ["Секретарь кафедры"])

    # Сроки — из таймеров движка (P7D/P14D из default_params), а не
    # "старт экземпляра + норматив в днях": раньше при отсутствии строки в
    # process_params_current срок был пуст, а у шагов без таймера — ложный.
    row = task_row("secretary", "approve_topics")
    remind, due = datetime.fromisoformat(row["remind_at"]), datetime.fromisoformat(row["due_at"])
    now = datetime.now(timezone.utc)
    check("срок approve_topics взят из таймеров: эскалация через 14 дн, напоминание через 7",
          abs((due - now) - timedelta(days=14)) < timedelta(minutes=5)
          and abs((due - remind) - timedelta(days=7)) < timedelta(seconds=1))
    check("свежая задача — «в срок»", row["urgency"] == "good")

    check("нормоконтролёр не может выполнить approve_topics -> 403", complete("normcontrol", "approve_topics") == 403)
    check("секретарь выполняет approve_topics -> 200", complete("secretary", "approve_topics") == 200)

    check("руководитель ВКР видит предзащиту", visible("supervisor") == ["report_2"])
    check("у шага без таймера (предзащита) срока нет", task_row("supervisor", "report_2")["due_at"] is None)
    check("секретарь не может выполнить предзащиту -> 403", complete("secretary", "report_2") == 403)
    check("руководитель ВКР выполняет предзащиту -> 200", complete("supervisor", "report_2") == 200)

    # Шаги дорожки «Студент» — только студенту, привязанному к ЭТОЙ защите.
    # Чужую защиту доводим до того же шага, чтобы проверка была содержательной.
    complete("secretary", "approve_topics", other_case)
    complete("supervisor", "report_2", other_case)
    check("чужая защита действительно на шаге студента",
          visible("admin", other_case) == ["publish_for_normcontrol"])
    check("свой студент видит publish_for_normcontrol", visible("student") == ["publish_for_normcontrol"])
    check("шаг чужой защиты студенту не виден", visible("student", other_case) == [])
    check("шаг чужой защиты студент выполнить не может -> 403",
          complete("student", "publish_for_normcontrol", other_case) == 403)
    check("секретарь не может выполнить шаг студента -> 403", complete("secretary", "publish_for_normcontrol") == 403)
    check("у шага студента есть срок из его таймеров", task_row("student", "publish_for_normcontrol")["due_at"] is not None)
    check("студент выполняет свой шаг -> 200", complete("student", "publish_for_normcontrol") == 200)

    check("теперь нормоконтролёр видит normcontrol", visible("normcontrol") == ["normcontrol"])
    check("секретарь не видит normcontrol", visible("secretary") == [])
    check("секретарь не может выполнить normcontrol -> 403", complete("secretary", "normcontrol") == 403)
    check("нормоконтролёр выполняет normcontrol -> 200", complete("normcontrol", "normcontrol") == 200)

    check("студент выполняет публикацию финальных версий -> 200", complete("student", "publish_final") == 200)
    check("у шага без таймера (admission_order) срока нет", task_row("secretary", "admission_order")["due_at"] is None)
    check("секретарь выполняет admission_order -> 200", complete("secretary", "admission_order") == 200)
    check("секретарь выполняет defense -> 200", complete("secretary", "defense") == 200)
    check("экземпляр завершён", orch.get_state(case_id)["completed"])

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

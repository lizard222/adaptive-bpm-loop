"""Кабинет задач — REST-слой (T-37, ФТ-С-4).

Задачи НЕ идут через Интерфейсного агента/FIPA (см. докстринг
agents/interface_agent.py) — у READY-задачи в оркестраторе нет "агента",
ожидающего ответа, поэтому эндпоинты вызывают Orchestrator напрямую.

Известное упрощение (задокументировано, не скрыто): список задач не
фильтруется по роли пользователя — BPMN-модели прототипа не размечены
дорожками (lanes), сопоставляющими задачу с ролью. Любой аутентифицированный
пользователь видит все READY-задачи всех активных экземпляров. Ролевая
фильтрация — расширение поверх реальных моделей кафедры (T-22/T-23), где
роли по дорожкам уже осмысленны.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Body, Depends, HTTPException

from orchestrator import Orchestrator
from orchestrator.engine import InstanceNotFound, TaskNotReady

from .auth import CurrentUser, get_current_user
from .config import settings

router = APIRouter(prefix="/tasks", tags=["tasks"])
_orchestrator = Orchestrator(settings.database_url)


@router.get("")
def list_tasks(user: CurrentUser = Depends(get_current_user)):
    """Все READY-задачи всех активных экземпляров (см. упрощение выше).

    due_at/remind_at — упрощение (задокументировано, не скрыто): считаются от
    process_instances.created_at (момент СТАРТА экземпляра), а не от момента,
    когда именно ЭТА задача стала READY — event_log вообще не логирует
    READY-переходы (orchestrator/engine.py::_log_transitions логирует только
    COMPLETED/CANCELLED). Для пилотных BPMN-моделей (bpmn/demo/*) это точно:
    их первая пользовательская задача становится READY в том же
    do_engine_steps(), которым стартует экземпляр (один линейный ранний шаг,
    без параллельных ветвей/шлюзов перед ней). Для моделей с шагами ДО первой
    задачи это приближение перестанет быть верным — потребует отдельного
    события "task_ready" в event_log (вне объёма текущей итерации).
    """
    items = []
    for case_id in _orchestrator.list_active_case_ids():
        state = _orchestrator.get_state(case_id)
        for task in state["tasks"]:
            if task["state"] != "READY":
                continue
            items.append({
                "case_id": case_id,
                "process_key": state["process_key"],
                "task_name": task["name"],
            })

    if items:
        case_ids = sorted({t["case_id"] for t in items})
        process_keys = sorted({t["process_key"] for t in items})
        with psycopg.connect(settings.database_url) as conn:
            created_by_case = dict(conn.execute(
                "SELECT case_id, created_at FROM process_instances WHERE case_id = ANY(%s)",
                (case_ids,),
            ).fetchall())
            params_by_key = {
                r[0]: {"reminder_days": r[1], "escalation_days": r[2]}
                for r in conn.execute(
                    "SELECT process_key, reminder_days, escalation_days FROM process_params_current "
                    "WHERE process_key = ANY(%s)",
                    (process_keys,),
                ).fetchall()
            }
        now = datetime.now(timezone.utc)
        for t in items:
            created_at = created_by_case.get(t["case_id"])
            params = params_by_key.get(t["process_key"])
            if created_at is None or params is None:
                t["due_at"] = t["remind_at"] = t["urgency"] = None
                continue
            due_at = created_at + timedelta(days=params["escalation_days"])
            remind_at = created_at + timedelta(days=params["reminder_days"])
            t["due_at"] = due_at.isoformat()
            t["remind_at"] = remind_at.isoformat()
            t["urgency"] = "critical" if now >= due_at else "warning" if now >= remind_at else "good"

    return {"tasks": items}


@router.post("/{case_id}/{task_name}/complete")
def complete_task(
    case_id: str,
    task_name: str,
    data: dict = Body(default={}),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        _orchestrator.complete_task(case_id, task_name, data=data or None, resource=user.username)
    except InstanceNotFound:
        raise HTTPException(status_code=404, detail=f"экземпляр {case_id!r} не найден")
    except TaskNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "case_id": case_id, "task_name": task_name, "by": user.username}

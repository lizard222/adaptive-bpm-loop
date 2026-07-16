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

from fastapi import APIRouter, Body, Depends, HTTPException

from orchestrator import Orchestrator
from orchestrator.engine import InstanceNotFound, TaskNotReady

from .auth import CurrentUser, get_current_user
from .config import settings

router = APIRouter(prefix="/tasks", tags=["tasks"])
_orchestrator = Orchestrator(settings.database_url)


@router.get("")
def list_tasks(user: CurrentUser = Depends(get_current_user)):
    """Все READY-задачи всех активных экземпляров (см. упрощение выше)."""
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

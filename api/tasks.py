"""Кабинет задач — REST-слой (T-37, ФТ-С-4).

Задачи НЕ идут через Интерфейсного агента/FIPA (см. докстринг
agents/interface_agent.py) — у READY-задачи в оркестраторе нет "агента",
ожидающего ответа, поэтому эндпоинты вызывают Orchestrator напрямую.

Роли (часть T-25): пользователь видит и может выполнить только READY-задачи
своей дорожки (lane) BPMN-модели — соответствие дорожек ролям и правило для
admin/шагов без дорожки см. api/task_access.py. Чужой шаг: в списке его нет,
POST .../complete отвечает 403.
"""
from __future__ import annotations

from datetime import datetime, timezone

import psycopg
from fastapi import APIRouter, Body, Depends, HTTPException

from orchestrator import Orchestrator
from orchestrator.engine import InstanceNotFound, TaskNotReady

from .auth import CurrentUser, get_current_user
from .deadlines import deadline_info
from .participants import STUDENT, participant, participants_by_case
from .task_access import can_act, resolve_lane
from .config import settings

router = APIRouter(prefix="/tasks", tags=["tasks"])
_orchestrator = Orchestrator(settings.database_url)


@router.get("")
def list_tasks(user: CurrentUser = Depends(get_current_user)):
    """READY-задачи активных экземпляров, видимые роли пользователя.

    due_at/remind_at — точные моменты срабатывания граничных таймеров шага,
    прочитанные из состояния движка (Orchestrator.get_state -> timers): их
    SpiffWorkflow фиксирует, когда шаг становится READY, из выражения таймера
    и параметров самого экземпляра. Поэтому верны и единицы (дни у vkr_defense,
    минуты у vkr_defense_fast), и точка отсчёта (момент готовности шага, а не
    старт экземпляра). Шаг без таймеров — без срока. Раньше срок считался
    как created_at экземпляра + норматив из process_params_current (всегда в
    днях) — это давало пустой срок при отсутствии строки параметров и
    ложный срок у шагов без таймеров.

    remind_at — самый ранний таймер шага, due_at — самый поздний (в рабочих
    моделях: напоминание и эскалация). При одном таймере remind_at = None.
    """
    items = []
    active = _orchestrator.list_active_case_ids()
    with psycopg.connect(settings.database_url) as conn:
        student_by_case = participants_by_case(conn, active, STUDENT)
    for case_id in active:
        state = _orchestrator.get_state(case_id)
        for task in state["tasks"]:
            if task["state"] != "READY":
                continue
            lane = resolve_lane(state["process_key"], task["name"], task.get("lane"))
            if not can_act(user.role, lane, user.username, student_by_case.get(case_id)):
                continue
            items.append({
                "case_id": case_id,
                "process_key": state["process_key"],
                "task_name": task["name"],
                "lane": lane,
                "_timers": task.get("timers") or [],
            })

    if items:
        case_ids = sorted({t["case_id"] for t in items})
        with psycopg.connect(settings.database_url) as conn:
            created_by_case = dict(conn.execute(
                "SELECT case_id, created_at FROM process_instances WHERE case_id = ANY(%s)",
                (case_ids,),
            ).fetchall())
        now = datetime.now(timezone.utc)
        for t in items:
            created_at = created_by_case.get(t["case_id"])
            # старт экземпляра — для сортировки «сначала старые/новые» в UI
            t["created_at"] = created_at.isoformat() if created_at else None
            t.update(deadline_info(t.pop("_timers"), now))

    return {"tasks": items}


@router.post("/{case_id}/{task_name}/complete")
def complete_task(
    case_id: str,
    task_name: str,
    data: dict = Body(default={}),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        state = _orchestrator.get_state(case_id)
    except InstanceNotFound:
        raise HTTPException(status_code=404, detail=f"экземпляр {case_id!r} не найден")
    ready = [t for t in state["tasks"] if t["name"] == task_name and t["state"] == "READY"]
    if ready:
        lane = resolve_lane(state["process_key"], task_name, ready[0].get("lane"))
        with psycopg.connect(settings.database_url) as conn:
            case_student = participant(conn, case_id, STUDENT)
        if not can_act(user.role, lane, user.username, case_student):
            raise HTTPException(
                status_code=403,
                detail=f"шаг «{task_name}» относится к дорожке {lane or '(без дорожки — только admin)'}; "
                       f"роль {user.role!r} не может его выполнить",
            )
    try:
        _orchestrator.complete_task(case_id, task_name, data=data or None, resource=user.username)
    except InstanceNotFound:
        raise HTTPException(status_code=404, detail=f"экземпляр {case_id!r} не найден")
    except TaskNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "case_id": case_id, "task_name": task_name, "by": user.username}

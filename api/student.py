"""«Моя защита» — экран студента (E13).

Студент видит только свои экземпляры (api/participants.py): этапы процесса
с отметкой «вы здесь», срок текущего этапа из таймеров движка, что сделать и
какие документы нужны (api/student_guide.py), и ленту уведомлений.

Лента строится из журнала событий ЭТОГО экземпляра (event_log): смена
этапа, напоминание, эскалация, сформированный документ. Отдельной рассылки
нет: Контролёр — агент, который в живой системе постоянно не запущен (см.
README, «постоянного рантайма агентов нет»), поэтому уведомление — это
человекочитаемое представление тех же событий, которые пишет оркестратор.
Внешних каналов (почта, мессенджеры) в прототипе нет сознательно.
"""
from __future__ import annotations

from datetime import datetime, timezone

import psycopg
from fastapi import APIRouter, Depends

from mining.control_points import VKR_DEFENSE_CONTROL_POINTS
from orchestrator import Orchestrator
from orchestrator.process_registry import PROCESS_REGISTRY

from .auth import CurrentUser, require_role
from .config import settings
from .deadlines import deadline_info
from .participants import STUDENT, cases_of
from .student_guide import GUIDE, GUIDE_BY_STEP
from .task_access import STUDENT_LANE, resolve_lane

router = APIRouter(prefix="/me", tags=["student"])
_orchestrator = Orchestrator(settings.database_url)

_REMIND = {cp.reminder_activity: cp.task for cp in VKR_DEFENSE_CONTROL_POINTS}
_ESCALATE = {cp.escalation_activity: cp.task for cp in VKR_DEFENSE_CONTROL_POINTS}


def _title(step: str) -> str:
    return GUIDE_BY_STEP[step]["title"] if step in GUIDE_BY_STEP else step


def _feed_item(activity: str, lifecycle: str, resource: str | None, attributes: dict) -> tuple[str, str] | None:
    """(текст, тон) или None — служебные события (таймеры, конечные события) в ленту не идут."""
    if activity == "process_instance":
        if lifecycle == "start":
            return "Запущен процесс защиты ВКР", "accent"
        return "Процесс защиты завершён", "neutral"
    if activity in _REMIND:
        return f"Напоминание: подходит срок этапа «{_title(_REMIND[activity])}»", "warning"
    if activity in _ESCALATE:
        return (f"Срок этапа «{_title(_ESCALATE[activity])}» истёк — уведомлён заведующий кафедрой", "critical")
    if activity == "document_generated":
        return f"Сформирован документ «{attributes.get('template', 'документ')}»", "accent"
    if activity in GUIDE_BY_STEP:
        # оркестратор пишет выполнение шага дважды: 'complete' из complete_task()
        # и 'completed' переходом состояния — в ленту идёт одно
        if lifecycle == "complete":
            who = " (вами)" if resource == attributes.get("_me") else ""
            return f"Этап «{_title(activity)}» выполнен{who}", "good"
        if lifecycle == "cancelled":
            return f"Этап «{_title(activity)}» прерван", "critical"
    return None


def _defense_view(conn: psycopg.Connection, case_id: str, username: str, now: datetime) -> dict:
    state = _orchestrator.get_state(case_id)
    tasks_by_name = {t["name"]: t for t in state["tasks"]}
    completed = state["completed"]

    stages = []
    current = None
    for g in GUIDE:
        task = tasks_by_name.get(g["step"])
        task_state = task["state"] if task else None
        if task_state == "COMPLETED":
            status = "done"
        elif task_state == "READY":
            status = "current"
        elif completed or task_state == "CANCELLED":
            status = "skipped"  # экземпляр завершился раньше (эскалация) — этап не пройден
        else:
            status = "upcoming"
        # дорожка — из модели реестра, а для процесса вне реестра — из самого
        # экземпляра (будущие шаги уже есть в дереве задач SpiffWorkflow)
        lane = resolve_lane(state["process_key"], g["step"], task["lane"] if task else None)
        stage = {**g, "status": status, "is_mine": lane == STUDENT_LANE,
                 **(deadline_info(task.get("timers") or [], now) if status == "current"
                    else {"due_at": None, "remind_at": None, "urgency": None})}
        stages.append(stage)
        if status == "current" and current is None:
            current = g["step"]

    rows = conn.execute(
        "SELECT activity, lifecycle, resource, ts, attributes FROM event_log WHERE case_id = %s ORDER BY ts DESC, event_id DESC",
        (case_id,),
    ).fetchall()
    feed = []
    for activity, lifecycle, resource, ts, attributes in rows:
        item = _feed_item(activity, lifecycle, resource, {**(attributes or {}), "_me": username})
        if item:
            feed.append({"ts": ts.isoformat(), "text": item[0], "tone": item[1]})

    reg = PROCESS_REGISTRY.get(state["process_key"])
    created = conn.execute("SELECT created_at FROM process_instances WHERE case_id = %s", (case_id,)).fetchone()
    return {
        "case_id": case_id,
        "process_key": state["process_key"],
        "kind": reg.kind if reg else None,
        "status": "completed" if completed else "active",
        "started_at": created[0].isoformat() if created else None,
        "current": current,
        "stages": stages,
        "feed": feed,
    }


@router.get("/defense")
def my_defense(user: CurrentUser = Depends(require_role("student"))):
    now = datetime.now(timezone.utc)
    with psycopg.connect(settings.database_url) as conn:
        case_ids = cases_of(conn, STUDENT, user.username)
        return {"defenses": [_defense_view(conn, c, user.username, now) for c in case_ids]}

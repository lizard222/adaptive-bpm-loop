"""Ручной запуск экземпляра процесса (E7, ФТ-А-... ): человек инициирует
новый case вне расписания Планировщика.

Тот же паттерн прямого вызова Orchestrator, что и api/tasks.py/
api/documents.py — нет "агента" на другом конце, ожидающего FIPA-ответа,
запуск синхронный. process_key/bpmn_file/process_id/default_params — ВСЕГДА
из orchestrator/process_registry.py, никогда с клиента (см. докстринг
модуля — иначе произвольный путь к файлу с клиента).
"""
from __future__ import annotations

import uuid

import psycopg
from fastapi import APIRouter, Body, Depends, HTTPException

from agents.model_store import current_model_file
from agents.params_store import get_current_params
from orchestrator import Orchestrator
from orchestrator.process_registry import PROCESS_REGISTRY

from .auth import DEMO_USERS, STAFF_ROLES, CurrentUser, require_role
from .milestones import MilestoneError, as_json, by_cases, parse, set_milestones
from .participants import STUDENT, bind
from .config import settings

router = APIRouter(prefix="/processes", tags=["processes"])
_orchestrator = Orchestrator(settings.database_url)

# Разумный потолок на "живой" разбор экземпляров (get_state ниже
# десериализует BpmnWorkflow на каждый активный экземпляр — недёшево на
# масштабе, см. тот же приём/предупреждение в api/tasks.py::list_tasks).
# Для реального сценария использования (drill-down по одному процессу
# конкретного пользователя) 50 самых свежих более чем достаточно.
_MAX_INSTANCES = 50


@router.get("")
def list_launchable(user: CurrentUser = Depends(require_role("dept_head", "secretary", "admin"))):
    """Что можно запустить вручную — реестр, а не произвольная строка с клиента."""
    return {
        "processes": [
            {"process_key": key, "has_params": reg.default_params is not None, "kind": reg.kind,
             "has_milestones": reg.milestone_unit is not None}
            for key, reg in PROCESS_REGISTRY.items()
        ],
    }


@router.get("/{process_key}/instances")
def list_instances(process_key: str, user: CurrentUser = Depends(require_role(*STAFF_ROLES))):
    """Drill-down для экрана «Процессы» (UI): не только агрегат
    активных/завершённых, но и конкретные case_id с текущим шагом. Доступ —
    как у /dashboard (любой аутентифицированный, read-only, решений здесь
    не принимается)."""
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            "SELECT case_id, status, created_at, updated_at FROM process_instances "
            "WHERE process_key = %s ORDER BY updated_at DESC LIMIT %s",
            (process_key, _MAX_INSTANCES),
        ).fetchall()

        milestones = by_cases(conn, [r[0] for r in rows])

    instances = []
    for case_id, status, created_at, updated_at in rows:
        current_tasks: list[str] = []
        if status == "active":
            state = _orchestrator.get_state(case_id)
            current_tasks = [t["name"] for t in state["tasks"] if t["state"] == "READY"]
        instances.append({
            "case_id": case_id,
            "status": status,
            "current_tasks": current_tasks,
            "milestones": as_json(milestones.get(case_id, {})),
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
        })
    reg = PROCESS_REGISTRY.get(process_key)
    return {"instances": instances, "milestones_supported": bool(reg and reg.milestone_unit)}


@router.post("/{process_key}/launch")
def launch(
    process_key: str,
    student: str | None = Body(default=None, embed=True),
    milestones: dict | None = Body(default=None, embed=True),
    attributes: dict = Body(default={}, embed=True),
    user: CurrentUser = Depends(require_role("dept_head", "secretary", "admin")),
):
    """student — логин студента, чья это защита (E13). Без него экземпляр
    запускается, но шаги дорожки «Студент» сможет выполнить только admin, а
    экран «Моя защита» его не покажет никому."""
    reg = PROCESS_REGISTRY.get(process_key)
    if reg is None:
        raise HTTPException(status_code=404, detail=f"неизвестный process_key: {process_key!r}")
    if student is not None and DEMO_USERS.get(student, {}).get("role") != "student":
        raise HTTPException(status_code=422, detail=f"{student!r} — не пользователь с ролью «студент»")
    # даты проверяются ДО запуска: ошибка в дате не должна оставлять экземпляр без дат
    try:
        dates = parse(milestones)
    except MilestoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if dates and reg.milestone_unit is None:
        raise HTTPException(status_code=422, detail=f"у процесса {process_key!r} нет ключевых дат")
    if "predefense_at" in dates and "defense_at" in dates and dates["predefense_at"] >= dates["defense_at"]:
        raise HTTPException(status_code=422, detail="предзащита должна быть раньше защиты")

    case_id = f"{process_key}-{uuid.uuid4().hex[:8]}"  # уникальность гарантирует сервер, не клиент
    initial_data = None
    if reg.default_params is not None:
        current = get_current_params(settings.database_url, process_key, reg.default_params)
        initial_data = current.as_initial_data()

    try:
        _orchestrator.start_instance(
            # E15: по последней версии модели (структурная адаптация), не по базовому файлу
            case_id, process_key, current_model_file(settings.database_url, process_key), reg.process_id,
            initial_data=initial_data,
            attributes={"launched_by": user.username, "manual": True, "student": student,
                        "initial_data": initial_data, **attributes},
        )
    except Exception as exc:  # noqa: BLE001 — NFR-4: любая ошибка запуска -> явный 500, не тишина (тот же принцип, что api/documents.py)
        raise HTTPException(status_code=500, detail=f"не удалось запустить процесс: {exc}")

    with psycopg.connect(settings.database_url) as conn:
        if student is not None:
            bind(conn, case_id, STUDENT, student)
            conn.commit()
        if dates:
            set_milestones(conn, case_id, dates, user.username)
    return {"ok": True, "case_id": case_id, "process_key": process_key, "student": student,
            "milestones": as_json(dates)}

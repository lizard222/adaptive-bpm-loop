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

from agents.params_store import get_current_params
from orchestrator import Orchestrator
from orchestrator.process_registry import PROCESS_REGISTRY

from .auth import CurrentUser, get_current_user, require_role
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
            {"process_key": key, "has_params": reg.default_params is not None, "kind": reg.kind}
            for key, reg in PROCESS_REGISTRY.items()
        ],
    }


@router.get("/{process_key}/instances")
def list_instances(process_key: str, user: CurrentUser = Depends(get_current_user)):
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
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
        })
    return {"instances": instances}


@router.post("/{process_key}/launch")
def launch(
    process_key: str,
    attributes: dict = Body(default={}),
    user: CurrentUser = Depends(require_role("dept_head", "secretary", "admin")),
):
    reg = PROCESS_REGISTRY.get(process_key)
    if reg is None:
        raise HTTPException(status_code=404, detail=f"неизвестный process_key: {process_key!r}")

    case_id = f"{process_key}-{uuid.uuid4().hex[:8]}"  # уникальность гарантирует сервер, не клиент
    initial_data = None
    if reg.default_params is not None:
        current = get_current_params(settings.database_url, process_key, reg.default_params)
        initial_data = current.as_initial_data()

    try:
        _orchestrator.start_instance(
            case_id, process_key, reg.bpmn_file, reg.process_id,
            initial_data=initial_data,
            attributes={"launched_by": user.username, "manual": True, "initial_data": initial_data, **attributes},
        )
    except Exception as exc:  # noqa: BLE001 — NFR-4: любая ошибка запуска -> явный 500, не тишина (тот же принцип, что api/documents.py)
        raise HTTPException(status_code=500, detail=f"не удалось запустить процесс: {exc}")

    return {"ok": True, "case_id": case_id, "process_key": process_key}

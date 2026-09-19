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

from fastapi import APIRouter, Body, Depends, HTTPException

from agents.params_store import get_current_params
from orchestrator import Orchestrator
from orchestrator.process_registry import PROCESS_REGISTRY

from .auth import CurrentUser, require_role
from .config import settings

router = APIRouter(prefix="/processes", tags=["processes"])
_orchestrator = Orchestrator(settings.database_url)


@router.get("")
def list_launchable(user: CurrentUser = Depends(require_role("dept_head", "secretary", "admin"))):
    """Что можно запустить вручную — реестр, а не произвольная строка с клиента."""
    return {
        "processes": [
            {"process_key": key, "has_params": reg.default_params is not None}
            for key, reg in PROCESS_REGISTRY.items()
        ],
    }


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

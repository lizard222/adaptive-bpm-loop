"""Кабинет документов — REST-слой (T-36 -> T-59).

Вызывает templates.render.render() НАПРЯМУЮ, минуя SPADE-агента
(agents/templater_agent.py) — см. докстринг templates/render.py:8-12, это
предусмотренный путь ("для прямого вызова в обход агента... из будущего
REST-эндпоинта"), тот же приём, что и в api/tasks.py (нет "агента",
ожидающего FIPA-ответа, на другом конце). Персистентный TemplaterAgent-процесс
для этого НЕ поднимается — это отдельная, сознательно отложенная задача
(долгоживущий рантайм агентов вообще не существует в прототипе).

Доступ: любой аутентифицированный пользователь — как у /tasks (см. докстринг
api/tasks.py про отсутствие дорожек в BPMN-моделях).
"""
from __future__ import annotations

from pathlib import Path

import psycopg
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse

from eventlog.documents import log_document_generated
from templates.render import TEMPLATES, missing_fields, render

from .auth import CurrentUser, get_current_user
from .config import settings

router = APIRouter(prefix="/documents", tags=["documents"])

_OUTPUT_DIR = Path(settings.documents_dir)
if not _OUTPUT_DIR.is_absolute():
    _OUTPUT_DIR = Path(__file__).resolve().parent.parent / _OUTPUT_DIR

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/templates")
def list_templates(user: CurrentUser = Depends(get_current_user)):
    return {
        "templates": [
            {"name": spec.name, "required_fields": list(spec.required_fields)}
            for spec in TEMPLATES.values()
        ],
    }


@router.post("/generate")
def generate(
    template: str = Body(embed=True),
    case_id: str = Body(embed=True),
    process_key: str = Body(embed=True),
    context: dict = Body(embed=True, default={}),
    user: CurrentUser = Depends(get_current_user),
):
    spec = TEMPLATES.get(template)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"неизвестный шаблон: {template!r}")
    missing = missing_fields(spec, context)
    if missing:
        raise HTTPException(status_code=422, detail={"missing_fields": missing})
    try:
        out_path = render(spec, context, _OUTPUT_DIR)
    except Exception as exc:  # noqa: BLE001 — NFR-4: любая ошибка рендера -> явный 500, не тишина
        raise HTTPException(status_code=500, detail=f"ошибка рендера: {exc}")

    with psycopg.connect(settings.database_url) as conn:
        event_id = log_document_generated(
            conn, case_id, process_key, spec.name, out_path, resource=user.username,
        )
        conn.commit()

    return {
        "id": event_id, "template": spec.name, "case_id": case_id,
        "process_key": process_key, "filename": out_path.name,
    }


@router.get("")
def list_documents(user: CurrentUser = Depends(get_current_user)):
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            "SELECT event_id, case_id, process_key, resource, ts, attributes->>'template' AS template "
            "FROM event_log WHERE activity = 'document_generated' ORDER BY ts DESC LIMIT 100"
        ).fetchall()
    return {
        "documents": [
            {
                "id": r[0], "case_id": r[1], "process_key": r[2],
                "generated_by": r[3], "generated_at": r[4].isoformat(), "template": r[5],
            }
            for r in rows
        ],
    }


@router.get("/{document_id}/download")
def download(document_id: int, user: CurrentUser = Depends(get_current_user)):
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute(
            "SELECT attributes->>'path' AS path FROM event_log "
            "WHERE event_id = %s AND activity = 'document_generated'",
            (document_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="документ не найден")
    path = Path(row[0])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="файл на диске отсутствует (мог быть удалён вручную)")
    return FileResponse(path, media_type=_DOCX_MEDIA_TYPE, filename=path.name)

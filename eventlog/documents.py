"""Запись события «документ сформирован» в event_log (T-36 -> T-59 REST).

Извлечено из agents/templater_agent.py.TemplaterAgent._log_generated, чтобы
агент и REST-эндпоинт (api/documents.py) писали ОДНУ и ту же вставку, а не
дублировали SQL. Принимает уже открытое соединение (как
orchestrator/engine.py::_log_event), а не database_url — вызывающий код сам
управляет транзакцией/коммитом.
"""
from __future__ import annotations

from pathlib import Path

import psycopg


def log_document_generated(
    conn: psycopg.Connection,
    case_id: str,
    process_key: str,
    template_name: str,
    out_path: Path,
    resource: str,
) -> int:
    row = conn.execute(
        "INSERT INTO event_log (case_id, process_key, activity, lifecycle, resource, attributes) "
        "VALUES (%s, %s, 'document_generated', 'complete', %s, %s) RETURNING event_id",
        (
            case_id, process_key, resource,
            psycopg.types.json.Json({"template": template_name, "path": str(out_path)}),
        ),
    ).fetchone()
    return row[0]

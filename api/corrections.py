"""Панель корректировок — REST-слой (T-37, ФТ-С-7.4).

В отличие от /tasks, здесь REST не вызывает ничего напрямую — только
читает/пишет pending_decisions. Реальный FIPA-обмен (отправка
accept-proposal/reject-proposal Аналитик-Адаптеру) выполняет отдельно
работающий agents/interface_agent.py (Dispatch), который подхватывает
решённые-но-неотправленные строки на следующем тике. Это НАМЕРЕННАЯ
развязка (REST и SPADE-агент — разные процессы, общаются только через БД),
не костыль — см. докстринг agents/interface_agent.py.
"""
from __future__ import annotations

import psycopg
from fastapi import APIRouter, Body, Depends, HTTPException

from .auth import CurrentUser, require_role
from .config import settings

router = APIRouter(prefix="/corrections", tags=["corrections"])


@router.get("/pending")
def list_pending(user: CurrentUser = Depends(require_role("dept_head", "admin"))):
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            "SELECT id, process_key, kind, target, justification, created_at "
            "FROM pending_decisions WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
    return {
        "pending": [
            {
                "id": r[0], "process_key": r[1], "kind": r[2], "target": r[3],
                "justification": r[4], "created_at": r[5].isoformat(),
            }
            for r in rows
        ],
    }


@router.post("/{decision_id}/decide")
def decide(
    decision_id: int,
    decision: str = Body(embed=True),
    user: CurrentUser = Depends(require_role("dept_head", "admin")),
):
    if decision not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="decision должно быть 'accept' или 'reject'")
    status_value = "accepted" if decision == "accept" else "rejected"
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute(
            "UPDATE pending_decisions SET status = %s, decided_by = %s, decided_at = now() "
            "WHERE id = %s AND status = 'pending' RETURNING id",
            (status_value, user.username, decision_id),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=409, detail="предложение не найдено или уже решено")
    return {"ok": True, "id": decision_id, "status": status_value}

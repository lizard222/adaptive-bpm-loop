"""Участники экземпляра процесса: кто конкретно участвует в защите (E13).

Хранение — таблица case_participants (db/init/006_case_participants.sql).
Сейчас используется одна роль в процессе — 'student'.
"""
from __future__ import annotations

import psycopg

STUDENT = "student"


def bind(conn: psycopg.Connection, case_id: str, role: str, username: str) -> None:
    conn.execute(
        "INSERT INTO case_participants (case_id, role, username) VALUES (%s, %s, %s) "
        "ON CONFLICT (case_id, role) DO UPDATE SET username = EXCLUDED.username",
        (case_id, role, username),
    )


def participant(conn: psycopg.Connection, case_id: str, role: str) -> str | None:
    row = conn.execute(
        "SELECT username FROM case_participants WHERE case_id = %s AND role = %s", (case_id, role)
    ).fetchone()
    return row[0] if row else None


def participants_by_case(conn: psycopg.Connection, case_ids: list[str], role: str) -> dict[str, str]:
    return dict(conn.execute(
        "SELECT case_id, username FROM case_participants WHERE case_id = ANY(%s) AND role = %s",
        (case_ids, role),
    ).fetchall())


def cases_of(conn: psycopg.Connection, role: str, username: str) -> list[str]:
    """Экземпляры, где пользователь участвует в данной роли — свежие первыми."""
    return [r[0] for r in conn.execute(
        "SELECT cp.case_id FROM case_participants cp JOIN process_instances pi USING (case_id) "
        "WHERE cp.role = %s AND cp.username = %s ORDER BY pi.created_at DESC",
        (role, username),
    ).fetchall()]

"""Чтение/запись текущих параметров процесса (E3, часть T-25).

Переиспользует experiment.params.ProcessParams и apply_corrections —
тот же самый маппинг «корректировка → параметр», что уже проверен в
эксперименте (D1/D3, experiment/DESIGN.md §4). Отдельного дублирующего
определения здесь нет намеренно: если логика применения корректировок
меняется, она меняется в одном месте.

process_params_current хранит СОСТОЯНИЕ (одна строка на процесс — "какие
параметры действуют сейчас"), applied_corrections (T-42) — ИСТОРИЮ
(журнал всех применённых корректировок). Это разные назначения, обе
таблицы нужны.
"""
from __future__ import annotations

import psycopg

from experiment.params import Correction, ProcessParams, apply_corrections


def get_current_params(database_url: str, process_key: str, default: ProcessParams) -> ProcessParams:
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "SELECT reminder_days, escalation_days FROM process_params_current WHERE process_key = %s",
            (process_key,),
        ).fetchone()
    if row is None:
        return default
    return ProcessParams(reminder_days=row[0], escalation_days=row[1])


def apply_and_store(
    database_url: str, process_key: str, default: ProcessParams, accepted: list[Correction], version: int,
) -> ProcessParams:
    """Читает текущие параметры, применяет принятые корректировки (та же
    функция, что и в offline-эксперименте), сохраняет новую версию.
    Вызывается Аналитик-Адаптером (T-42) после применения корректировок."""
    current = get_current_params(database_url, process_key, default)
    updated = apply_corrections(current, accepted)
    with psycopg.connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO process_params_current (process_key, reminder_days, escalation_days, version)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (process_key) DO UPDATE
                SET reminder_days = EXCLUDED.reminder_days,
                    escalation_days = EXCLUDED.escalation_days,
                    version = EXCLUDED.version,
                    updated_at = now()
            """,
            (process_key, updated.reminder_days, updated.escalation_days, version),
        )
        conn.commit()
    return updated

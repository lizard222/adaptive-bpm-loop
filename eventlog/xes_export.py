"""Экспорт event_log в XES (T-32, ФТ-С-5.3).

XES (eXtensible Event Stream) — стандарт IEEE для журналов процессов, вход для
pm4py и любого другого инструмента process mining. Отображение колонок —
по конвенции pm4py: case:concept:name / concept:name / time:timestamp /
org:resource / lifecycle:transition.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import psycopg
import pm4py


def load_event_log_df(
    database_url: str,
    process_key: str | None = None,
    case_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Читает event_log из PostgreSQL, отдаёт DataFrame в колонках pm4py."""
    query = "SELECT case_id, process_key, activity, lifecycle, resource, ts, attributes FROM event_log"
    conditions, params = [], []
    if process_key is not None:
        conditions.append("process_key = %s")
        params.append(process_key)
    if case_ids:
        conditions.append("case_id = ANY(%s)")
        params.append(case_ids)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY ts"

    with psycopg.connect(database_url) as conn:
        df = pd.read_sql(query, conn, params=params or None)

    if df.empty:
        raise ValueError("event_log пуст для заданного фильтра — нечего экспортировать")

    df = df.rename(columns={
        "case_id": "case:concept:name",
        "activity": "concept:name",
        "ts": "time:timestamp",
        "resource": "org:resource",
        "lifecycle": "lifecycle:transition",
    })
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
    # jsonb-словарь как есть ломает конвертер XES (он трактует dict-значение как уже
    # вложенный XES-атрибут и падает на KeyError: 'value'). Храним как JSON-строку —
    # содержимое не теряется, просто не разворачивается в дерево атрибутов XES.
    df["attributes"] = df["attributes"].apply(lambda a: json.dumps(a, ensure_ascii=False) if a else "")
    return df


def export_xes(
    database_url: str,
    output_path: Path,
    process_key: str | None = None,
    case_ids: list[str] | None = None,
) -> int:
    """Экспортирует журнал в файл XES. Возвращает число выгруженных событий."""
    df = load_event_log_df(database_url, process_key=process_key, case_ids=case_ids)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pm4py.write_xes(df, str(output_path))
    return len(df)


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1]))
    from api.config import settings  # noqa: E402

    parser = argparse.ArgumentParser(description="Экспорт event_log в XES")
    parser.add_argument("output", type=Path, help="путь к выходному .xes файлу")
    parser.add_argument("--process", dest="process_key", default=None, help="фильтр по process_key")
    args = parser.parse_args()

    n = export_xes(settings.database_url, args.output, process_key=args.process_key)
    print(f"Экспортировано {n} событий -> {args.output}")

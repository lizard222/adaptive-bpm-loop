"""Ключевые даты защиты: предзащита и защита конкретного студента (E14).

Раньше система знала только относительные сроки («через 14 дней после начала
шага»), а у шагов, чей срок в регламенте задан календарной датой (предзащита,
«не позднее 10 дней до защиты», заседание ГЭК), срока не было вовсе. Теперь
секретарь назначает даты экземпляру — при запуске или позже, — и:

  * из них вычисляются моменты таймеров шагов со сроком от даты
    (mining.control_points.VKR_DEFENSE_DATE_POINTS) и кладутся в данные
    экземпляра — таймеры timeDate модели читают готовые значения;
  * перенос даты переносит и сроки, в том числе у уже взведённых таймеров
    (Orchestrator.update_data);
  * каждое назначение и перенос — событие milestones_set в журнале (с прежним
    и новым значением): студент видит это в ленте, история не теряется;
  * текущие значения — в case_milestones (для показа без разбора движка).

Сдвиги заданы в единицах модели (ProcessRegistration.milestone_unit): дни у
vkr_defense, минуты у тестовой vkr_defense_fast.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import psycopg
from fastapi import APIRouter, Body, Depends, HTTPException

from mining.control_points import VKR_DEFENSE_DATE_POINTS
from orchestrator import Orchestrator
from orchestrator.process_registry import PROCESS_REGISTRY

from .auth import STAFF_ROLES, CurrentUser, require_role
from .config import settings
from .student_guide import GUIDE

MILESTONES = ("predefense_at", "defense_at")
MILESTONE_TITLES = {"predefense_at": "предзащиты", "defense_at": "защиты"}
EVENT = "milestones_set"
EDIT_ROLES = ("secretary", "dept_head", "admin")

router = APIRouter(prefix="/cases", tags=["milestones"])
_orchestrator = Orchestrator(settings.database_url)


class MilestoneError(ValueError):
    pass


def parse(values: dict | None) -> dict[str, datetime]:
    """Проверяет ввод: только известные даты, ISO 8601 с часовым поясом.
    Пустые значения пропускаются (даты можно назначать по одной)."""
    result: dict[str, datetime] = {}
    for key, raw in (values or {}).items():
        if key not in MILESTONES:
            raise MilestoneError(f"неизвестная дата: {key!r} (ожидается {', '.join(MILESTONES)})")
        if raw in (None, ""):
            continue
        try:
            at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            raise MilestoneError(f"{key}: не дата в формате ISO 8601: {raw!r}") from None
        if at.tzinfo is None:
            raise MilestoneError(f"{key}: укажите часовой пояс (например, 2027-06-20T09:00:00+03:00)")
        result[key] = at
    return result


def timer_fields(milestones: dict[str, datetime], unit: timedelta) -> dict[str, str]:
    """Моменты таймеров шагов со сроком от даты — поля данных экземпляра."""
    fields: dict[str, str] = {}
    for point in VKR_DEFENSE_DATE_POINTS:
        anchor = milestones.get(point.anchor)
        if anchor is None:
            continue
        fields[point.remind_field] = (anchor + point.remind_offset * unit).isoformat()
        fields[point.due_field] = (anchor + point.due_offset * unit).isoformat()
    return fields


def unit_label(unit: timedelta | None) -> str:
    return "мин" if unit is not None and unit < timedelta(hours=1) else "дн."


def planned(milestones: dict[str, datetime], unit: timedelta | None) -> dict[str, dict]:
    """Плановые даты этапов по регламенту (student_guide.GUIDE["plan"])."""
    result: dict[str, dict] = {}
    if unit is None:
        return result
    for g in GUIDE:
        if "plan" not in g:
            continue
        anchor, offset = g["plan"]
        at = milestones.get(anchor)
        if at is None:
            continue
        if offset == 0:
            rule = f"дата {MILESTONE_TITLES[anchor]}"
        else:
            rule = f"за {abs(offset)} {unit_label(unit)} до {MILESTONE_TITLES[anchor]}"
        result[g["step"]] = {"at": (at + offset * unit).isoformat(), "rule": rule}
    return result


def current(conn: psycopg.Connection, case_id: str) -> dict[str, datetime]:
    return dict(conn.execute(
        "SELECT milestone, at FROM case_milestones WHERE case_id = %s", (case_id,)
    ).fetchall())


def by_cases(conn: psycopg.Connection, case_ids: list[str]) -> dict[str, dict[str, datetime]]:
    result: dict[str, dict[str, datetime]] = {}
    for case_id, milestone, at in conn.execute(
        "SELECT case_id, milestone, at FROM case_milestones WHERE case_id = ANY(%s)", (case_ids,)
    ).fetchall():
        result.setdefault(case_id, {})[milestone] = at
    return result


def as_json(milestones: dict[str, datetime]) -> dict[str, str | None]:
    return {m: milestones[m].isoformat() if m in milestones else None for m in MILESTONES}


def set_milestones(conn: psycopg.Connection, case_id: str, values: dict[str, datetime], username: str) -> dict:
    """Назначает/переносит даты экземпляра. Возвращает итоговые даты.
    MilestoneError — процесс без дат, экземпляр завершён, предзащита не раньше защиты."""
    row = conn.execute(
        "SELECT process_key, status FROM process_instances WHERE case_id = %s", (case_id,)
    ).fetchone()
    if row is None:
        raise LookupError(case_id)
    process_key, status = row
    reg = PROCESS_REGISTRY.get(process_key)
    if reg is None or reg.milestone_unit is None:
        raise MilestoneError(f"у процесса {process_key!r} нет ключевых дат")
    if status != "active":
        raise MilestoneError("экземпляр завершён — даты больше не меняются")

    before = current(conn, case_id)
    merged = {**before, **values}
    if "predefense_at" in merged and "defense_at" in merged and merged["predefense_at"] >= merged["defense_at"]:
        raise MilestoneError("предзащита должна быть раньше защиты")
    changes = {
        m: {"from": before[m].isoformat() if m in before else None, "to": at.isoformat()}
        for m, at in values.items() if before.get(m) != at
    }
    if not changes:
        return as_json(merged)

    data = {**{m: at.isoformat() for m, at in merged.items()}, **timer_fields(merged, reg.milestone_unit)}
    # Сначала движок (данные + пересчёт таймеров + событие в журнале), потом
    # таблица: не удалось обновить экземпляр — даты в таблице не меняются.
    _orchestrator.update_data(case_id, data, activity=EVENT, resource=username, attributes={"changes": changes})
    for m in changes:
        conn.execute(
            "INSERT INTO case_milestones (case_id, milestone, at, set_by) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (case_id, milestone) DO UPDATE SET at = EXCLUDED.at, set_by = EXCLUDED.set_by, set_at = now()",
            (case_id, m, merged[m], username),
        )
    conn.commit()
    return as_json(merged)


def _view(conn: psycopg.Connection, case_id: str) -> dict:
    row = conn.execute("SELECT process_key FROM process_instances WHERE case_id = %s", (case_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"экземпляр {case_id!r} не найден")
    reg = PROCESS_REGISTRY.get(row[0])
    unit = reg.milestone_unit if reg else None
    ms = current(conn, case_id)
    return {"case_id": case_id, "supported": unit is not None, "milestones": as_json(ms),
            "planned": planned(ms, unit), "unit": unit_label(unit)}


@router.get("/{case_id}/milestones")
def get_milestones(case_id: str, user: CurrentUser = Depends(require_role(*STAFF_ROLES))):
    with psycopg.connect(settings.database_url) as conn:
        return _view(conn, case_id)


@router.put("/{case_id}/milestones")
def put_milestones(
    case_id: str,
    values: dict = Body(...),
    user: CurrentUser = Depends(require_role(*EDIT_ROLES)),
):
    """Тело: {"predefense_at": ISO|null, "defense_at": ISO|null}; null/пусто — не менять."""
    try:
        parsed = parse(values)
        with psycopg.connect(settings.database_url) as conn:
            set_milestones(conn, case_id, parsed, user.username)
            return _view(conn, case_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"экземпляр {case_id!r} не найден")
    except MilestoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

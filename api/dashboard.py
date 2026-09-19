"""Дашборд контура адаптации — REST-слой (T-37, обзорный экран).

Только чтение — никаких решений здесь не принимается (это остаётся за
/corrections). Доступен любому аутентифицированному пользователю: это
обзор состояния процессов, а не панель управления с полномочиями.

process_key объединяется как union трёх источников (process_instances,
process_params_current, analysis_reports) — процесс с активными
экземплярами, но без ни одного цикла анализа, всё равно должен попасть
в список, просто с params/latest_report = null.

agents — честный статус "когда агент последний раз что-то сделал" по 5
РЕАЛЬНЫМ агентам прототипа (никаких выдуманных "предикторов"/"NLP-агентов"),
вычисленный по существующим данным, а не по факту реально живущего процесса
агента — постоянного рантайма агентов в прототипе нет вообще (это отдельная,
сознательно отложенная задача).
"""
from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from orchestrator.process_registry import PROCESS_REGISTRY

from .auth import CurrentUser, get_current_user
from .config import settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Контролер: имена активностей напоминания/эскалации различаются по BPMN-модели
# (mining/control_points.py — DEMO_CONTROL_POINTS/EXPERIMENT_CONTROL_POINTS
# используют remind/escalate; WORKLOAD_CONTROL_POINTS — remind_calc/escalate_calc/
# remind_dist/escalate_dist; VKR_DEFENSE_CONTROL_POINTS —
# remind_topics/escalate_topics/remind_normcontrol/escalate_normcontrol).
# Жёстко перечисляем известные имена — тот же приём, что и в самих per-model
# реестрах control_points.py, не строим динамический разбор BPMN ради этого
# виджета. Новая модель с другими именами таймеров потребует добавить их сюда же.
_CONTROLLER_ACTIVITIES = (
    "remind", "escalate", "remind_calc", "escalate_calc", "remind_dist", "escalate_dist",
    "remind_topics", "escalate_topics", "remind_normcontrol", "escalate_normcontrol",
)

# Только реальные агенты прототипа — никогда не выдуманные ("предиктор"/
# "NLP-агент" не существуют, показывать их как "активные" было бы неправдой.
_AGENT_LABELS = [
    ("scheduler", "Планировщик"),
    ("controller", "Контролер"),
    ("analyst_adapter", "Аналитик-Адаптер"),
    ("interface", "Интерфейсный агент"),
    ("templater", "Шаблонизатор"),
]


@router.get("/summary")
def summary(include_all: bool = False, user: CurrentUser = Depends(get_current_user)):
    """include_all=false (по умолчанию) — показывает только РЕАЛЬНЫЕ процессы
    системы (ключи из orchestrator/process_registry.py, сейчас — только
    vkr_defense). Без этого фильтра дашборд захламлён сотнями process_key,
    накопленных за месяцы смоук-тестов/эксперимента (demo_process_*,
    experiment_*, workload_planning_days_*, vkr_defense_<run_id> и т.п.) —
    они получают уникальный process_key НАРОЧНО (чтобы параллельные тесты не
    видели чужое состояние через общий event_log), но для человека на
    "боевом" экране это чистый шум, не относящийся к суженной теме. История
    из БД не удаляется — include_all=true возвращает её целиком, для
    отладки/проверки данных экспериментов напрямую через API."""
    with psycopg.connect(settings.database_url) as conn:
        active_counts = dict(
            conn.execute(
                "SELECT process_key, count(*) FROM process_instances "
                "WHERE status = 'active' GROUP BY process_key"
            ).fetchall()
        )
        # Без этого процесс, у которого ВСЕ экземпляры уже завершились и ни
        # разу не запускался анализ (нет своей строки в process_params_current/
        # analysis_reports — например, ручной запуск вне эксперимента), выпадал
        # из объединения active_counts | params_by_key | reports_by_key и
        # полностью исчезал из дашборда, хотя вся история осталась в БД.
        completed_counts = dict(
            conn.execute(
                "SELECT process_key, count(*) FROM process_instances "
                "WHERE status = 'completed' GROUP BY process_key"
            ).fetchall()
        )
        # first_seen/last_seen — для сортировки "сначала новые/старые" на
        # экране «Процессы» (UI, редизайн). Один запрос по той же таблице,
        # что active/completed_counts — ключи будут ровно тем же множеством.
        seen_rows = conn.execute(
            "SELECT process_key, min(created_at), max(updated_at) FROM process_instances "
            "GROUP BY process_key"
        ).fetchall()
        seen_by_key = {r[0]: {"first_seen": r[1].isoformat(), "last_seen": r[2].isoformat()} for r in seen_rows}

        params_rows = conn.execute(
            "SELECT process_key, reminder_days, escalation_days, version, updated_at "
            "FROM process_params_current"
        ).fetchall()
        params_by_key = {
            r[0]: {
                "reminder_days": r[1], "escalation_days": r[2],
                "version": r[3], "updated_at": r[4].isoformat(),
            }
            for r in params_rows
        }
        report_rows = conn.execute(
            "SELECT DISTINCT ON (process_key) report_id, process_key, n_cases, "
            "fitness, precision_, report, created_at "
            "FROM analysis_reports ORDER BY process_key, created_at DESC"
        ).fetchall()
        reports_by_key = {}
        for r in report_rows:
            control_points = [
                {"task": task, **stats} for task, stats in (r[5].get("control_points") or {}).items()
            ]
            reports_by_key[r[1]] = {
                "report_id": r[0], "n_cases": r[2], "fitness": r[3], "precision": r[4],
                "created_at": r[6].isoformat(), "control_points": control_points,
            }
        decision_rows = conn.execute(
            "SELECT id, process_key, kind, target, status, decided_by, created_at, decided_at "
            "FROM pending_decisions WHERE status != 'pending' "
            "ORDER BY decided_at DESC LIMIT 20"
        ).fetchall()

        agent_last_active = {
            "scheduler": conn.execute("SELECT max(created_at) FROM process_instances").fetchone()[0],
            "controller": conn.execute(
                "SELECT max(ts) FROM event_log WHERE activity = ANY(%s)", (list(_CONTROLLER_ACTIVITIES),)
            ).fetchone()[0],
            "analyst_adapter": conn.execute("SELECT max(created_at) FROM analysis_reports").fetchone()[0],
            "interface": conn.execute(
                "SELECT max(decided_at) FROM pending_decisions WHERE decided_at IS NOT NULL"
            ).fetchone()[0],
            "templater": conn.execute(
                "SELECT max(ts) FROM event_log WHERE activity = 'document_generated'"
            ).fetchone()[0],
        }

    process_keys = (
        set(active_counts) | set(completed_counts) | set(params_by_key) | set(reports_by_key) | set(seen_by_key)
    )
    if not include_all:
        process_keys &= set(PROCESS_REGISTRY)
    processes = [
        {
            "process_key": key,
            "active_instances": active_counts.get(key, 0),
            "completed_instances": completed_counts.get(key, 0),
            "params": params_by_key.get(key),
            "latest_report": reports_by_key.get(key),
            "first_seen": seen_by_key.get(key, {}).get("first_seen"),
            "last_seen": seen_by_key.get(key, {}).get("last_seen"),
        }
        for key in process_keys
    ]
    # Активные — наверх (только что запущенный процесс легко потерять среди
    # десятков старых process_key из смоук-тестов, если сортировать просто по
    # алфавиту); дальше — по числу завершённых (у процесса есть история);
    # алфавит — только как последний тай-брейк для стабильности порядка.
    processes.sort(key=lambda p: (-p["active_instances"], -p["completed_instances"], p["process_key"]))
    recent_decisions = [
        {
            "id": r[0], "process_key": r[1], "kind": r[2], "target": r[3], "status": r[4],
            "decided_by": r[5], "created_at": r[6].isoformat(),
            "decided_at": r[7].isoformat() if r[7] else None,
        }
        for r in decision_rows
    ]
    agents = [
        {"key": key, "label": label, "last_active": agent_last_active[key].isoformat() if agent_last_active[key] else None}
        for key, label in _AGENT_LABELS
    ]
    return {"processes": processes, "recent_decisions": recent_decisions, "agents": agents}
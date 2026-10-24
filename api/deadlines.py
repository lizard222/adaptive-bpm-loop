"""Срок шага по его граничным таймерам (общий расчёт для /tasks и /me/defense).

timers — из Orchestrator.get_state(): точные моменты срабатывания, которые
SpiffWorkflow фиксирует, когда шаг становится READY. remind_at — самый
ранний таймер, due_at — самый поздний (в рабочих моделях: напоминание и
эскалация); при одном таймере remind_at = None; без таймеров срока нет.
"""
from __future__ import annotations

from datetime import datetime


def deadline_info(timers: list[dict], now: datetime) -> dict:
    if not timers:
        return {"due_at": None, "remind_at": None, "urgency": None}
    due_at = datetime.fromisoformat(timers[-1]["fire_at"])
    remind_at = datetime.fromisoformat(timers[0]["fire_at"]) if len(timers) > 1 else None
    if now >= due_at:
        urgency = "critical"
    elif remind_at is not None and now >= remind_at:
        urgency = "warning"
    else:
        urgency = "good"
    return {
        "due_at": due_at.isoformat(),
        "remind_at": remind_at.isoformat() if remind_at else None,
        "urgency": urgency,
    }

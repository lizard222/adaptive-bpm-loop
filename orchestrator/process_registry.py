"""Реестр процессов, доступных для запуска (E7): единый источник истины для
(а) REST-эндпоинта ручного запуска (api/processes.py) и (б) будущего списка
LaunchRule Планировщика (agents/scheduler_agent.py) — оба должны
использовать ОДНИ И ТЕ ЖЕ bpmn_file/process_id/default_params, чтобы не
расходиться (ручной запуск с другим BPMN-файлом, чем плановый, был бы
багом).

bpmn_file — ВСЕГДА берётся из этого реестра, никогда из пользовательского
ввода: REST-эндпоинт не должен принимать произвольный путь с клиента
(иначе — чтение произвольных файлов сервером по указке клиента).

Существующие демо-процессы (demo_process/workload_planning/experiment)
намеренно НЕ включены сюда: они существуют только для смоук-тестов и
эксперимента, не для ручного запуска из кабинета задач.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from experiment.params import ProcessParams

if TYPE_CHECKING:
    from agents.scheduler_agent import LaunchRule

_BPMN_DIR = Path(__file__).resolve().parent.parent / "bpmn" / "demo"


@dataclass(frozen=True)
class ProcessRegistration:
    process_key: str
    bpmn_file: Path
    process_id: str | None
    default_params: ProcessParams | None  # None — модель без параметризованных таймеров
    interval_seconds: float  # используется ТОЛЬКО для LaunchRule Планировщика


PROCESS_REGISTRY: dict[str, ProcessRegistration] = {
    "vkr_defense": ProcessRegistration(
        process_key="vkr_defense",
        bpmn_file=_BPMN_DIR / "vkr_defense.bpmn",
        process_id="vkr_defense",
        default_params=ProcessParams(reminder_days=7, escalation_days=14),
        interval_seconds=3600,
    ),
}


def build_launch_rules() -> list["LaunchRule"]:
    """Собирает LaunchRule Планировщика из этого реестра — единственное место,
    где перечислены процессы для планового автозапуска. Не вызывается сейчас
    автоматически ни из чего (постоянного рантайма агентов в прототипе ещё
    нет — см. docstring agents/scheduler_agent.py), но именно эту функцию
    следует использовать, когда появится реальный процесс-раннер
    Планировщика, а не перечислять LaunchRule вручную повторно.

    Существующие смоук-тесты (agents/smoke_test.py,
    agents/params_flow_smoke_test.py, agents/second_process_smoke_test.py)
    намеренно НЕ переведены на эту функцию — они конструируют свои
    LaunchRule с process_key, уникальным на каждый прогон
    (f"demo_process_{RUN_ID}"), чтобы параллельные тесты не видели чужое
    состояние через общий event_log; build_launch_rules() возвращает
    фиксированные ключи и для такого сценария не подходит.
    """
    from agents.scheduler_agent import LaunchRule  # локальный импорт: избегаем цикла agents<->orchestrator

    return [
        LaunchRule(
            process_key=reg.process_key,
            bpmn_file=reg.bpmn_file,
            process_id=reg.process_id,
            interval_seconds=reg.interval_seconds,
            base_params=reg.default_params,
        )
        for reg in PROCESS_REGISTRY.values()
    ]

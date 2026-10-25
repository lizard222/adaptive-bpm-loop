"""Версии модели процесса — структурная адаптация (E15).

Параметрическая адаптация (agents/params_store.py) меняет числа: сроки
напоминания и эскалации. Структурная меняет саму модель: принятая
корректировка add_checkpoint ставит контрольную точку (напоминание +
эскалацию) на шаг, у которого срока не было. Это новая версия модели:

  * хранится целиком в process_model_versions (BPMN XML + список добавленных
    точек) — версия воспроизводима, даже если генератор потом изменится;
  * новые экземпляры запускаются по последней версии (current_model_file),
    уже идущие доходят по своей — SpiffWorkflow хранит модель в состоянии
    экземпляра;
  * анализ следующего цикла видит добавленную точку (control_points_for), а
    Контролёр начинает за ней следить (ParamsListener, agents/controller_agent.py).

Версия 0 — базовая модель из реестра (orchestrator/process_registry.py).
Процессы без model_builder в реестре (эксперимент, демо) не версионируются:
для них add_checkpoint остаётся сигналом, как раньше.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import psycopg

from mining.control_points import ControlPoint, added_control_point
from mining.corrections import Correction
from orchestrator.process_registry import PROCESS_REGISTRY

from .params_store import get_current_params

# Кэш файлов версий для движка (он грузит модель из файла). Источник истины —
# БД: при отсутствии файла он восстанавливается из bpmn_xml.
GENERATED_DIR = Path(__file__).resolve().parent.parent / "bpmn" / "generated"


def current_version(database_url: str, process_key: str) -> tuple[int, tuple[str, ...]]:
    """(номер версии, добавленные контрольные точки); (0, ()) — базовая модель."""
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "SELECT version, added_checkpoints FROM process_model_versions "
            "WHERE process_key = %s ORDER BY version DESC LIMIT 1",
            (process_key,),
        ).fetchone()
    return (row[0], tuple(row[1])) if row else (0, ())


def current_model_file(database_url: str, process_key: str) -> Path:
    """Файл модели, по которой запускать новые экземпляры процесса из реестра."""
    reg = PROCESS_REGISTRY[process_key]
    version, _ = current_version(database_url, process_key)
    if version == 0:
        return reg.bpmn_file
    path = GENERATED_DIR / f"{process_key}.v{version}.bpmn"
    if not path.exists():
        with psycopg.connect(database_url) as conn:
            xml = conn.execute(
                "SELECT bpmn_xml FROM process_model_versions WHERE process_key = %s AND version = %s",
                (process_key, version),
            ).fetchone()[0]
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(xml, encoding="utf-8")
    return path


def control_points_for(database_url: str, process_key: str, base: list[ControlPoint]) -> list[ControlPoint]:
    """Контрольные точки текущей версии: базовые + добавленные корректировками."""
    _, added = current_version(database_url, process_key)
    known = {cp.task for cp in base}
    return [*base, *(added_control_point(t) for t in added if t not in known)]


def apply_structural(
    database_url: str, process_key: str, accepted: list[Correction], params_version: int | None,
) -> tuple[int, tuple[str, ...]] | None:
    """Принятые add_checkpoint -> новая версия модели. Возвращает (версия,
    добавленные точки) или None, если модель не изменилась: процесс без
    model_builder, точка на шаге уже есть, или шаг для неё не подходит (у
    него уже есть срок — например, add_checkpoint по признаку «пропуск»)."""
    reg = PROCESS_REGISTRY.get(process_key)
    if reg is None or reg.model_builder is None:
        return None
    version, added = current_version(database_url, process_key)
    new_points = []
    for c in accepted:
        if c.kind != "add_checkpoint" or c.target in added or c.target in new_points:
            continue
        try:
            reg.model_builder((*added, *new_points, c.target))
        except ValueError:
            continue  # шагу контрольная точка не нужна или невозможна — корректировка остаётся сигналом
        new_points.append(c.target)
    if not new_points:
        return None
    points = (*added, *new_points)
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "INSERT INTO process_model_versions (process_key, version, added_checkpoints, bpmn_xml, params_version) "
            "VALUES (%s, %s, %s, %s, %s)",
            (process_key, version + 1, list(points), reg.model_builder(points), params_version),
        )
        conn.commit()
    return version + 1, points


def step_norm(database_url: str, process_key: str) -> timedelta | None:
    """Норма длительности шага без контроля (E15): текущий срок напоминания
    процесса — столько система ждёт исполнителя на контролируемых шагах,
    прежде чем напомнить. Единица — та же, что у таймеров модели (у тестовой
    vkr_defense_fast — минуты; ProcessRegistration.milestone_unit совпадает с
    единицей её таймеров)."""
    reg = PROCESS_REGISTRY.get(process_key)
    if reg is None or reg.default_params is None:
        return None
    params = get_current_params(database_url, process_key, reg.default_params)
    return params.reminder_days * (reg.milestone_unit or timedelta(days=1))

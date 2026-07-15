"""Алгоритм «расхождения → корректировки» (T-41, ФТ-С-7.2, ФТ-С-7.3).

Главный научный результат работы: превращение результатов конвейера анализа
(mining/conveyor.py, T-40) в конкретные предложения по изменению параметров
процесса на следующий цикл. Пороги классификации — конфигурируемые параметры
метода (Thresholds); их влияние на качество адаптации исследуется отдельно
(T-52, анализ чувствительности), здесь — сам механизм классификации.

Классификация расхождений (ФТ-С-7.2, три типа):
  1. систематическая просрочка шага — доля эскалаций по контрольной точке
     выше порога -> сдвиг срока запуска этапа (kind="shift_start");
     доля напоминаний без эскалации выше порога, но эскалаций мало ->
     более мягкий сигнал: пересмотр нормативной длительности
     (kind="review_duration") — норматив занижен, но процесс пока справляется;
  2. систематический пропуск шага — доля пропусков (model move из
     conformance checking) выше порога -> добавление контрольной точки
     (kind="add_checkpoint");
  3. узкое место — НЕ реализовано в v1: требует данных о загрузке нескольких
     исполнителей одной роли, которых нет в текущей закрытой синтетической
     системе (один синтетический исполнитель на шаг, simgen/executor.py).
     Появится вместе с многоресурсными моделями (T-22/T-23).

Функция чистая: ConveyorReport -> list[Correction], ничего не пишет и не
применяет. Применение (создание новой версии параметров, отправка `propose`
человеку) — задача агента Аналитик-Адаптер (T-42, human-in-the-loop, ФТ-С-7.4).
"""
from __future__ import annotations

from dataclasses import dataclass

from .conveyor import ConveyorReport


@dataclass(frozen=True)
class Thresholds:
    """Пороги систематичности — конфигурируемые параметры метода (ФТ-С-7.2)."""

    escalation_fraction: float = 0.15  # доля эскалаций по шагу -> систематическая просрочка
    late_fraction: float = 0.30        # доля напоминаний (без эскалации) -> норматив занижен
    skip_fraction: float = 0.20        # доля пропусков шага -> систематический пропуск
    min_sample_size: int = 5           # меньше — корректировки не предлагаются (шум выборки)


@dataclass
class Correction:
    process_key: str
    kind: str   # "shift_start" | "review_duration" | "add_checkpoint"
    target: str  # id задачи/шага, к которому относится корректировка
    evidence: dict
    justification: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.target}: {self.justification}"

    def to_dict(self) -> dict:
        return {
            "process_key": self.process_key, "kind": self.kind, "target": self.target,
            "evidence": self.evidence, "justification": self.justification,
        }


def propose_corrections(report: ConveyorReport, thresholds: Thresholds = Thresholds()) -> list[Correction]:
    corrections: list[Correction] = []

    if report.n_cases < thresholds.min_sample_size:
        return corrections  # выборка мала — предлагать корректировки преждевременно

    for cp in report.control_points.values():
        if cp.escalated_fraction >= thresholds.escalation_fraction:
            corrections.append(Correction(
                process_key=report.process_key,
                kind="shift_start",
                target=cp.task,
                evidence={
                    "escalated_fraction": round(cp.escalated_fraction, 3),
                    "escalated": cp.escalated, "n_cases": cp.n_cases,
                },
                justification=(
                    f"Эскалация сработала в {cp.escalated_fraction:.0%} экземпляров "
                    f"({cp.escalated} из {cp.n_cases}) — систематическая просрочка шага «{cp.task}». "
                    f"Предлагается сдвинуть срок запуска этапа раньше на следующий цикл."
                ),
            ))
        elif cp.late_fraction >= thresholds.late_fraction:
            corrections.append(Correction(
                process_key=report.process_key,
                kind="review_duration",
                target=cp.task,
                evidence={"late_fraction": round(cp.late_fraction, 3), "n_cases": cp.n_cases},
                justification=(
                    f"Напоминание сработало в {cp.late_fraction:.0%} экземпляров шага «{cp.task}», "
                    f"но до эскалации системно не доходит — нормативная длительность, по-видимому, "
                    f"занижена. Предлагается пересмотреть норматив."
                ),
            ))

    for activity, count in report.skipped_activities.items():
        skip_fraction = count / report.n_cases
        if skip_fraction >= thresholds.skip_fraction:
            corrections.append(Correction(
                process_key=report.process_key,
                kind="add_checkpoint",
                target=activity,
                evidence={"skip_fraction": round(skip_fraction, 3), "count": count, "n_cases": report.n_cases},
                justification=(
                    f"Шаг «{activity}» пропущен (расхождение с моделью) в {skip_fraction:.0%} "
                    f"экземпляров ({count} из {report.n_cases}). Предлагается добавить контрольную точку."
                ),
            ))

    return corrections

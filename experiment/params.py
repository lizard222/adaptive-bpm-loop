"""Параметры процесса для эксперимента (D1/T-50) и правило «корректировка ->
изменение параметра» (D3/T-51).

ВАЖНОЕ ОГРАНИЧЕНИЕ, зафиксированное здесь явно, а не спрятанное в коде:
текущая архитектура не моделирует АБСОЛЮТНЫЙ внешний дедлайн (например, дату
заседания ГЭК) — только относительные таймеры от момента, когда шаг стал
READY (ФТ-С-6, граничные события BPMN). Поэтому «сдвиг срока запуска этапа
раньше» (shift_start) в реальном процессе означал бы больше календарного
времени до фиксированной внешней даты, но в текущей симуляции это не может
быть буквально смоделировано без абсолютного дедлайна в модели процесса
(появится вместе с T-22/T-23 и полной версионируемой process_params, T-25).

Для ЭТОГО эксперимента shift_start и review_duration обе транслируются в
расширение соответствующего ОТНОСИТЕЛЬНОГО окна (escalation_days или
reminder_days) — разными шагами. Это упрощение конкретного механизма
адаптации для целей измеримого эксперимента, а не имитация реального сдвига
календарной даты; методологическая оговорка должна быть отражена в тексте
диссертации при описании дизайна эксперимента.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from mining.corrections import Correction

# Шаги корректировки — конфигурируемые константы метода (аналогично
# Thresholds в mining/corrections.py); влияние величины шага на скорость
# сходимости адаптации можно исследовать отдельно (T-52).
SHIFT_START_STEP_DAYS = 3      # систематическая эскалация -> расширить escalation_days
REVIEW_DURATION_STEP_DAYS = 2  # систематические напоминания -> расширить reminder_days


@dataclass(frozen=True)
class ProcessParams:
    reminder_days: int
    escalation_days: int

    def as_initial_data(self) -> dict:
        return {"reminder_days": self.reminder_days, "escalation_days": self.escalation_days}


def apply_corrections(params: ProcessParams, corrections: list[Correction]) -> ProcessParams:
    """Чистая функция: текущие параметры + принятые корректировки этого цикла
    -> параметры следующего цикла. shift_start и review_duration — единственные
    типы, применяемые здесь автоматически; add_checkpoint не меняет численные
    параметры (ФТ-С-7.3: часть корректировок — только сигнал, не действие)."""
    reminder_days = params.reminder_days
    escalation_days = params.escalation_days
    for c in corrections:
        if c.kind == "shift_start":
            escalation_days += SHIFT_START_STEP_DAYS
        elif c.kind == "review_duration":
            reminder_days += REVIEW_DURATION_STEP_DAYS
    return replace(params, reminder_days=reminder_days, escalation_days=escalation_days)

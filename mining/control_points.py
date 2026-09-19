"""Конфигурация контрольных точек процесса (используется conveyor.py и
corrections.py, T-40/T-41).

Контрольная точка — задача BPMN, к которой привязаны граничные таймерные
события "напоминание"/"эскалация" (ФТ-С-6). Пока не построена версионируемая
таблица process_params (T-25), это минимальный эквивалент метаданных
процесса, специфичных для анализа: список контрольных точек передаётся явно
вызывающим кодом, а не парсится из BPMN — состав таймеров и так определяет
автор модели, дублировать эту логику разбором XML не требуется.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ControlPoint:
    task: str
    reminder_activity: str | None = None
    escalation_activity: str | None = None


# Контрольная точка демо-модели (bpmn/demo/demo_process_days.bpmn) — для
# смоук-тестов; контрольные точки реальных моделей появятся вместе с T-22/T-23.
DEMO_CONTROL_POINTS = [
    ControlPoint(task="review_request", reminder_activity="remind", escalation_activity="escalate"),
]

# Второй демо-процесс (bpmn/demo/workload_planning_days.bpmn, B6/T-38) — ДВЕ
# последовательные контрольные точки, проверяет, что оркестратор/конвейер/
# алгоритм корректировок работают с несколькими шагами одного процесса, а не
# только с одним. Подключение — этот список + BPMN-файл, код не менялся.
WORKLOAD_CONTROL_POINTS = [
    ControlPoint(task="calculate_load", reminder_activity="remind_calc", escalation_activity="escalate_calc"),
    ControlPoint(task="distribute_load", reminder_activity="remind_dist", escalation_activity="escalate_dist"),
]

# Модель эксперимента (bpmn/demo/experiment_process.bpmn, D1-D3/T-50-T-51) —
# длительности таймеров параметризованы (reminder_days/escalation_days),
# контрольная точка та же, что у demo_process_days структурно.
EXPERIMENT_CONTROL_POINTS = [
    ControlPoint(task="review_request", reminder_activity="remind", escalation_activity="escalate"),
]

# Модель "Защита ВКР" (bpmn/demo/vkr_defense.bpmn) — первая реальная модель
# процесса, к которому сужена тема (не абстрактная заглушка). Первая, что
# сочетает НЕСКОЛЬКО контрольных точек (как WORKLOAD_CONTROL_POINTS) с
# ПАРАМЕТРИЗОВАННЫМИ таймерами (как EXPERIMENT_CONTROL_POINTS) — обе точки
# используют одни и те же reminder_days/escalation_days процесса, отдельных
# параметров на точку пока нет (ProcessParams в experiment/params.py —
# процесс-глобальная, не по-шаговая; расширение до по-шаговых параметров —
# вне объёма этой минимальной модели). Шаги admission_order/defense
# сознательно без контрольных точек — см. шапку vkr_defense.bpmn.
VKR_DEFENSE_CONTROL_POINTS = [
    ControlPoint(task="approve_topics", reminder_activity="remind_topics", escalation_activity="escalate_topics"),
    ControlPoint(task="normcontrol", reminder_activity="remind_normcontrol", escalation_activity="escalate_normcontrol"),
]

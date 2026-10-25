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
# ПАРАМЕТРИЗОВАННЫМИ таймерами (как EXPERIMENT_CONTROL_POINTS) — все точки
# используют одни и те же reminder_days/escalation_days процесса, отдельных
# параметров на точку пока нет (ProcessParams в experiment/params.py —
# процесс-глобальная, не по-шаговая; расширение до по-шаговых параметров —
# вне объёма этой минимальной модели). Шаги report_2/publish_final/
# admission_order/defense без контрольных точек — см. шапку vkr_defense.bpmn.
VKR_DEFENSE_CONTROL_POINTS = [
    ControlPoint(task="approve_topics", reminder_activity="remind_topics", escalation_activity="escalate_topics"),
    # Шаг студента (E13): просрочки самого студента теперь видны контуру
    # адаптации — раньше в модели не было ни одного шага студента.
    ControlPoint(task="publish_for_normcontrol", reminder_activity="remind_publish", escalation_activity="escalate_publish"),
    ControlPoint(task="normcontrol", reminder_activity="remind_normcontrol", escalation_activity="escalate_normcontrol"),
]


@dataclass(frozen=True)
class DateControlPoint:
    """Контрольная точка, привязанная к календарной дате экземпляра (E14).

    В отличие от ControlPoint, срок считается не от момента, когда шаг стал
    READY, а от даты-якоря конкретной защиты (дата предзащиты или защиты),
    которую назначает секретарь: remind_offset/due_offset — сдвиг от якоря в
    единицах модели (дни у vkr_defense, минуты у vkr_defense_fast).
    Моменты срабатывания считает api/milestones.py и кладёт в данные
    экземпляра (поля remind_field/due_field), таймер timeDate в BPMN только
    читает готовое значение — в выражениях таймеров SpiffWorkflow нет
    datetime. Эскалация необрывающая: завкафедрой уведомлён, шаг продолжается.

    В контур адаптации (VKR_DEFENSE_CONTROL_POINTS) эти точки НЕ входят:
    корректировки сейчас меняют относительные сроки (reminder_days/
    escalation_days), а срок от календарной даты ими не сдвигается.
    """

    task: str
    anchor: str  # "predefense_at" | "defense_at"
    remind_offset: int
    due_offset: int
    reminder_activity: str
    escalation_activity: str

    @property
    def remind_field(self) -> str:
        return f"{self.task}_remind_at"

    @property
    def due_field(self) -> str:
        return f"{self.task}_due_at"


# Сроки — по каталогу (ВРБ/МД, см. bpmn/tobe/TRACEABILITY.md): финальные
# версии — не позднее 10 дней до защиты, приказ о допуске — не позднее 14 дней
# до заседания ГЭК, уведомление о защите — за 3 дня. Предзащита и защита —
# результат должен быть отмечен не позже следующего дня.
VKR_DEFENSE_DATE_POINTS = [
    DateControlPoint("report_2", "predefense_at", -1, 1, "remind_report_2", "escalate_report_2"),
    DateControlPoint("publish_final", "defense_at", -12, -10, "remind_publish_final", "escalate_publish_final"),
    DateControlPoint("admission_order", "defense_at", -16, -14, "remind_admission", "escalate_admission"),
    DateControlPoint("defense", "defense_at", -3, 1, "remind_defense", "escalate_defense"),
]

# Значение таймера «дата не назначена»: выражение timeDate в модели берёт
# поле из данных экземпляра, а если его нет — этот момент, который не
# наступит. Оркестратор не показывает такие таймеры как срок
# (orchestrator/engine.py::_boundary_timers).
UNSET_DATE = "9999-12-31T00:00:00+00:00"


# --- Структурная адаптация (E15): контрольная точка, добавленная корректировкой ---

def added_control_point(task: str) -> ControlPoint:
    """Контрольная точка, которую добавляет принятая корректировка add_checkpoint.

    Имена активностей выводятся из id шага по соглашению (remind_<шаг>/
    escalate_<шаг>) — так их знают генератор модели, анализ, Контролёр и лента
    студента без отдельного реестра. Таймеры — те же reminder_days/
    escalation_days процесса, что и у остальных относительных точек.
    """
    return ControlPoint(task=task, reminder_activity=f"remind_{task}", escalation_activity=f"escalate_{task}")


@dataclass(frozen=True)
class MonitoredStep:
    """Шаг без контрольной точки, за длительностью которого следит анализ (E15).

    Длительность шага в экземпляре = от завершения предыдущего шага (момент,
    когда этот стал готов к выполнению — в последовательной модели они
    совпадают; переход в READY журнал не пишет) до завершения этого.
    Систематически долгий шаг без контроля — повод добавить контрольную точку.
    """

    task: str
    previous: str


# Шаги рабочей модели без какого-либо срока. «Отзыв руководителя и рецензия»
# (МД.19) — в каталоге «параллельно с проверкой на плагиат», конкретного срока
# регламент не задаёт. Анализ исключает отсюда шаги, на которые контрольная
# точка уже добавлена (mining.conveyor.analyze_cycle).
VKR_DEFENSE_MONITORED_STEPS = [
    MonitoredStep(task="supervisor_review", previous="publish_final"),
]

"""Генератор to-be модели «Защита ВКР» (T-22) и таблицы трассировки.

Один источник описания -> два артефакта, которые не могут разойтись:
  vkr_defense_tobe.bpmn — исполняемая BPMN-модель (SpiffWorkflow, через
                          orchestrator.Orchestrator), с дорожками-ролями;
  TRACEABILITY.md       — таблица «мероприятие каталога -> элемент модели».

Источник мероприятий — «Бизнес-процессы кафедры САПРиПК (версия 3.0)»,
таблицы БПБак.ВРБ (24 строки) и БПМаг.МД (26 строк). В каталоге у шифров
нет порядковых номеров («БПБак.ВРБ.» без числа, у МД шифр в строках вовсе
пуст), поэтому ВРБ.01–ВРБ.24 и МД.01–МД.26 — нумерация по порядку строк,
назначенная здесь.

Запуск: python bpmn/tobe/build_tobe.py  (из корня adaptive-bpm-loop)
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

OUT_DIR = Path(__file__).resolve().parent

# --- каталог (as-is): № -> (мероприятие, срок по каталогу) -------------------
VRB = {
    1: ("Название тем студентам и распределение по руководителям ВКР", "сентябрь"),
    2: ("Выпуск приказа о назначении руководителей и тем ВКР (1С:СЭД)", "октябрь"),
    3: ("Выпуск приказа о составе комиссии ГАК", "ноябрь"),
    4: ("Формирование расписаний еженедельных консультаций научных руководителей", "сентябрь"),
    5: ("Проведение консультации по выполнению ВКР (методичка, семинары)", "октябрь"),
    6: ("Проведение 1-го промежуточного отчёта по ВКР", "декабрь"),
    7: ("Проведение 2-го промежуточного отчёта по ВКР (предзащита)", "апрель"),
    8: ("Оформление выговоров студентам, не прошедшим промежуточный отчёт", "апрель"),
    9: ("Формирование графика защит на текущий год", "апрель"),
    10: ("Выпуск приказа на изменение тем", "февраль"),
    11: ("Ходатайство кафедры о выпускниках на красный диплом", "не указан"),
    12: ("Подготовка документов на оплату работы сторонних членов ГАК", "не указан"),
    13: ("Публикация ПЗ и ТЗ в Moodle для проверки и нормоконтроля", "июнь, за 2 недели до защиты"),
    14: ("Проведение нормоконтроля", "июнь"),
    15: ("Публикация финальных версий ПЗ и ТЗ в Moodle", "июнь, не позднее 10 дней до защиты"),
    16: ("Распоряжение о назначении ответственного за проверку на плагиат", "не указан"),
    17: ("Проверка на плагиат (Антиплагиат, справка)", "июнь, не позднее 10 дней до защиты"),
    18: ("Организация защит ВКР (график, уведомления ГАК и студентов)", "за 3 дня до защиты"),
    19: ("Проведение защит", "в день защиты"),
    20: ("Оформление протоколов (шифр в каталоге пуст)", "не указан"),
    21: ("Заполнение зачёток (шифр в каталоге пуст)", "не указан"),
    22: ("Оформление отчёта по результатам защит (шифр в каталоге пуст)", "в течение 1 недели после защит"),
    23: ("Сбор данных о трудоустройстве выпускников", "1 месяц после защиты"),
    24: ("Сдача документов в архив (5-летней давности)", "1 месяц после защиты"),
}
MD = {
    1: ("Распределение магистров по преподавателям (темы МД)", "сентябрь; утверждение тем не позднее 6 мес. до ГИА"),
    2: ("Выпуск приказа о назначении руководителей и тем МД (АСУД)", "октябрь"),
    3: ("Выпуск приказа о составе комиссии ГАК", "ноябрь"),
    4: ("Формирование расписаний еженедельных консультаций", "октябрь"),
    5: ("Формирование плана публикаций", "сентябрь"),
    6: ("Утверждение индивидуальных планов магистранта", "сентябрь"),
    7: ("Проведение консультации по выполнению МД (методичка, семинар)", "сентябрь"),
    8: ("Проведение 1-го промежуточного отчёта по МД", "декабрь"),
    9: ("Проведение 2-го промежуточного отчёта по МД (предзащита)", "апрель"),
    10: ("Оформление выговоров студентам, не прошедшим промежуточный отчёт", "апрель"),
    11: ("Формирование графика защит на текущий год", "апрель"),
    12: ("Выпуск приказа на изменение тем МД", "февраль; не позднее 2 мес. до ГИА"),
    13: ("Публикация ПЗ и ТЗ в Moodle для проверки и нормоконтроля", "июнь, за 2 недели до защиты"),
    14: ("Проведение нормоконтроля", "июнь"),
    15: ("Публикация финальных версий ПЗ и ТЗ в Moodle", "июнь, не позднее 10 дней до защиты"),
    16: ("Распоряжение о назначении ответственного за проверку на плагиат", "не указан"),
    17: ("Приказ о допуске к защите", "не позднее 14 дней до первого заседания ГЭК"),
    18: ("Проверка на плагиат, справка и протокол", "июнь, не позднее 10 дней до защиты"),
    19: ("Подготовка отзыва руководителя и рецензии", "параллельно с проверкой на плагиат"),
    20: ("Передача переплетённой ВКР, отзыва, рецензии и справки в ГЭК", "не позднее 2 календарных дней до защиты"),
    21: ("Проверка секретарём комплекта документов (этика, справка, размещение, зачётная книжка)", "не указан"),
    22: ("Организация защит МД (график, уведомления, подготовка протоколов)", "за 3 дня до защиты"),
    23: ("Проведение защит МД", "в день защиты"),
    24: ("Оформление отчёта по результатам защит", "в течение 1 недели после защит"),
    25: ("Сбор данных о трудоустройстве выпускников", "1 месяц после защиты"),
    26: ("Сдача документов в архив (5-летней давности)", "не указан"),
}

# --- дорожки (роли). system_role — роль в api/auth.py, если она есть -------
LANES = {
    "lane_dept_head": ("Заведующий кафедрой", "dept_head"),
    "lane_secretary": ("Секретарь кафедры", "secretary"),
    "lane_supervisor": ("Руководитель ВКР", "supervisor"),
    "lane_normcontrol": ("Нормоконтролёр", "normcontrol"),
    "lane_plagiarism": ("Ответственный за проверку на заимствования", None),
    "lane_student": ("Студент", "student"),
    "lane_commission": ("ГЭК", None),
}

# --- пользовательские задачи to-be модели ---------------------------------
# id -> (название, дорожка, ВРБ-номера, МД-номера, уровень, шаг рабочей модели vkr_defense)
# уровень: "оба" / "только магистратура" / "только бакалавриат" — по каталогу.
TASKS = {
    # уровень выпуска
    "distribute_topics": ("Распределение тем и руководителей", "lane_secretary", [1], [1], "оба", "approve_topics (объединено)"),
    "approve_topics": ("Приказ о назначении руководителей и тем", "lane_secretary", [2], [2], "оба", "approve_topics"),
    "gak_order": ("Состав ГЭК и приказ о комиссии", "lane_dept_head", [3], [3], "оба", None),
    "consult_schedule": ("Расписание консультаций руководителей", "lane_secretary", [4], [4], "оба", None),
    "seminars": ("Методичка и семинары о подготовке ВКР", "lane_secretary", [5], [7], "оба", None),
    "publication_plan": ("План публикаций магистрантов", "lane_supervisor", [], [5], "только магистратура", None),
    "individual_plans": ("Утверждение индивидуальных планов магистрантов", "lane_dept_head", [], [6], "только магистратура", None),
    "defense_schedule": ("График защит на текущий год", "lane_secretary", [9], [11], "оба", None),
    "plagiarism_responsible": ("Распоряжение о назначении ответственного за проверку на заимствования", "lane_dept_head", [16], [16], "оба", None),
    "organize_defenses": ("Организация защит: запись, уведомление ГЭК и студентов", "lane_secretary", [18], [22], "оба", None),
    "honors": ("Ходатайство о выпускниках на красный диплом", "lane_secretary", [11], [], "только бакалавриат", None),
    "gek_payment": ("Документы на оплату сторонних членов ГЭК", "lane_secretary", [12], [], "только бакалавриат", None),
    "report_results": ("Отчёт по результатам защит", "lane_secretary", [22], [24], "оба", None),
    "employment": ("Сбор данных о трудоустройстве выпускников", "lane_secretary", [23], [25], "оба", None),
    "archive": ("Сдача документов в архив", "lane_secretary", [24], [26], "оба", None),
    # уровень студента (многоэкземплярный подпроцесс)
    "report_1": ("1-й промежуточный отчёт", "lane_supervisor", [6], [8], "оба", None),
    "topic_change_order": ("Приказ на изменение темы", "lane_secretary", [10], [12], "оба", None),
    "report_2": ("Предзащита (2-й промежуточный отчёт)", "lane_supervisor", [7], [9], "оба", "report_2"),
    "reprimand": ("Оформление выговора", "lane_secretary", [8], [10], "оба", None),
    "publish_for_normcontrol": ("Публикация ПЗ и ТЗ в Moodle для нормоконтроля", "lane_student", [13], [13], "оба", "publish_for_normcontrol"),
    "normcontrol": ("Нормоконтроль", "lane_normcontrol", [14], [14], "оба", "normcontrol"),
    "publish_final": ("Публикация финальных версий в Moodle", "lane_student", [15], [15], "оба", "publish_final"),
    "plagiarism_check": ("Проверка на заимствования и справка", "lane_plagiarism", [17], [18], "оба", None),
    "supervisor_review": ("Отзыв руководителя и рецензия", "lane_supervisor", [], [19], "только магистратура", None),
    "admission_order": ("Приказ о допуске к защите", "lane_secretary", [], [17], "оба (см. примечание)", "admission_order"),
    "handover_to_gek": ("Передача ВКР, отзыва, рецензии и справки в ГЭК", "lane_secretary", [], [20], "только магистратура", None),
    "docs_check": ("Проверка комплекта документов секретарём", "lane_secretary", [], [21], "только магистратура", None),
    "defense": ("Защита ВКР", "lane_commission", [19], [23], "оба", "defense"),
    "protocols": ("Протоколы защиты и зачётные книжки", "lane_secretary", [20, 21], [22], "оба", None),
}
STUDENT_TASKS = {
    "report_1", "topic_change_order", "report_2", "reprimand", "publish_for_normcontrol", "normcontrol",
    "publish_final", "plagiarism_check", "supervisor_review", "admission_order", "handover_to_gek",
    "docs_check", "defense", "protocols",
}

# Контрольные точки: необрывающий граничный таймер -> эскалация завкафедрой.
# (в рабочей модели vkr_defense эскалация прерывающая — упрощение для
# измеримости эксперимента; в to-be эскалация шаг не отменяет)
CONTROL_POINTS = {
    "distribute_topics": "topics_days",
    "normcontrol": "normcontrol_days",
    "plagiarism_check": "plagiarism_days",
    "admission_order": "admission_days",
}

NOTES = {
    "distribute_topics": "В рабочей модели ВРБ.01/02 объединены в один шаг approve_topics.",
    "admission_order": "В каталоге БПБак.ВРБ приказа о допуске нет (есть только в МД.17); в to-be — для обоих "
                       "уровней: шаг есть в рабочей модели и в шаблоне templates/vkr_admission_order.docx. "
                       "Расхождение каталога стоит уточнить на кафедре.",
    "protocols": "ВРБ.20 и ВРБ.21 объединены; в МД протоколы входят в МД.22.",
    "organize_defenses": "Порядок «организация защит раньше самих защит» задаётся календарём (за 3 дня), "
                         "а не потоком: это ветка уровня выпуска, параллельная подпроцессам студентов.",
    "report_1": "Проводят рецензенты из преподавателей кафедры; дорожка «Руководитель ВКР» — ближайшая "
                "роль системы.",
    "report_2": "То же, что для 1-го отчёта.",
    "gek_payment": "По каталогу только в ВРБ; для МД не указано.",
    "honors": "По каталогу только в ВРБ.",
}


def _x(s: str) -> str:
    return escape(s, {'"': "&quot;"})


class Flow:
    def __init__(self):
        self.lines: list[str] = []
        self.n = 0

    def seq(self, a: str, b: str, cond: str | None = None, fid: str | None = None) -> str:
        self.n += 1
        fid = fid or f"flow_{self.n}"
        if cond:
            self.lines.append(
                f'<bpmn:sequenceFlow id="{fid}" sourceRef="{a}" targetRef="{b}">'
                f'<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">{_x(cond)}</bpmn:conditionExpression>'
                f"</bpmn:sequenceFlow>"
            )
        else:
            self.lines.append(f'<bpmn:sequenceFlow id="{fid}" sourceRef="{a}" targetRef="{b}"/>')
        return fid


def _task(tid: str) -> str:
    return f'<bpmn:userTask id="{tid}" name="{_x(TASKS[tid][0])}"/>'


def _control_point(tid: str, var: str, fl: Flow) -> list[str]:
    name = TASKS[tid][0]
    out = [
        f'<bpmn:boundaryEvent id="{tid}_timer" name="Срок: {_x(name)}" attachedToRef="{tid}" cancelActivity="false">'
        f"<bpmn:timerEventDefinition><bpmn:timeDuration xsi:type=\"bpmn:tFormalExpression\">f'P{{{var}}}D'"
        f"</bpmn:timeDuration></bpmn:timerEventDefinition></bpmn:boundaryEvent>",
        f'<bpmn:scriptTask id="escalate_{tid}" name="Эскалация завкафедрой: {_x(name)}">'
        f"<bpmn:script>escalated_{tid} = True</bpmn:script></bpmn:scriptTask>",
        f'<bpmn:endEvent id="end_escalate_{tid}"/>',
    ]
    fl.seq(f"{tid}_timer", f"escalate_{tid}")
    fl.seq(f"escalate_{tid}", f"end_escalate_{tid}")
    return out


def _chain(fl: Flow, *ids: str) -> None:
    for a, b in zip(ids, ids[1:]):
        fl.seq(a, b)


def _xor(gid: str, default_flow: str | None = None, name: str = "") -> str:
    d = f' default="{default_flow}"' if default_flow else ""
    n = f' name="{_x(name)}"' if name else ""
    return f'<bpmn:exclusiveGateway id="{gid}"{n}{d}/>'


def _optional(fl: Flow, split: str, join: str, cond: str, body: list[str], question: str) -> list[str]:
    """split --cond--> body... --> join; split --default--> join."""
    default_id = f"{split}_default"
    fl.seq(split, body[0], cond)
    _chain(fl, *body)
    fl.seq(body[-1], join)
    fl.seq(split, join, fid=default_id)
    return [_xor(split, default_id, question), _xor(join)]


def build_student_subprocess(fl: Flow) -> list[str]:
    el: list[str] = [
        '<bpmn:subProcess id="student_vkr" name="Подготовка и защита ВКР студента">',
        '<bpmn:multiInstanceLoopCharacteristics isSequential="false">'
        "<bpmn:loopDataInputRef>students</bpmn:loopDataInputRef>"
        '<bpmn:inputDataItem id="student"/></bpmn:multiInstanceLoopCharacteristics>',
        '<bpmn:startEvent id="student_start"/>',
    ]
    for tid in sorted(STUDENT_TASKS):
        el.append(_task(tid))
    el += _optional(fl, "gw_topic_change", "gw_topic_change_join", "topic_change_needed == True",
                    ["topic_change_order"], "Нужно изменить тему?")
    el += _optional(fl, "gw_report_2", "gw_report_2_join", "report_2_ok == False",
                    ["reprimand"], "Предзащита не пройдена?")
    el += ['<bpmn:parallelGateway id="ps_checks"/>', '<bpmn:parallelGateway id="pj_checks"/>']
    el += _optional(fl, "gw_review", "gw_review_join", "level == 'master'",
                    ["supervisor_review"], "Магистратура?")
    el += _optional(fl, "gw_handover", "gw_handover_join", "level == 'master'",
                    ["handover_to_gek", "docs_check"], "Магистратура?")
    el.append('<bpmn:endEvent id="student_end"/>')

    _chain(fl, "student_start", "report_1", "gw_topic_change")
    _chain(fl, "gw_topic_change_join", "report_2", "gw_report_2")
    _chain(fl, "gw_report_2_join", "publish_for_normcontrol", "normcontrol", "publish_final", "ps_checks")
    _chain(fl, "ps_checks", "plagiarism_check", "pj_checks")
    _chain(fl, "ps_checks", "gw_review")
    _chain(fl, "gw_review_join", "pj_checks")
    _chain(fl, "pj_checks", "admission_order", "gw_handover")
    _chain(fl, "gw_handover_join", "defense", "protocols", "student_end")

    for tid in ("normcontrol", "plagiarism_check", "admission_order"):
        el += _control_point(tid, CONTROL_POINTS[tid], fl)
    # потоки подпроцесса должны лежать внутри него
    el += fl.lines
    fl.lines = []
    el.append("</bpmn:subProcess>")
    return el


def build_bpmn() -> str:
    fl = Flow()
    body: list[str] = []

    lanes_xml = ['<bpmn:laneSet id="lanes">']
    by_lane: dict[str, list[str]] = {lid: [] for lid in LANES}
    for tid, (_, lane, *_rest) in TASKS.items():
        by_lane[lane].append(tid)
    for tid in CONTROL_POINTS:
        by_lane["lane_dept_head"].append(f"escalate_{tid}")
    for lid, (name, _) in LANES.items():
        refs = "".join(f"<bpmn:flowNodeRef>{r}</bpmn:flowNodeRef>" for r in by_lane[lid])
        lanes_xml.append(f'<bpmn:lane id="{lid}" name="{_x(name)}">{refs}</bpmn:lane>')
    lanes_xml.append("</bpmn:laneSet>")

    body += build_student_subprocess(fl)

    body.append('<bpmn:startEvent id="start" name="Начало учебного года"/>')
    for tid in TASKS:
        if tid not in STUDENT_TASKS:
            body.append(_task(tid))
    body += [
        '<bpmn:parallelGateway id="ps_setup"/>', '<bpmn:parallelGateway id="pj_setup"/>',
        '<bpmn:parallelGateway id="ps_main"/>', '<bpmn:parallelGateway id="pj_main"/>',
        '<bpmn:endEvent id="end" name="Выпуск завершён"/>',
    ]
    body += _optional(fl, "gw_master_plans", "gw_master_plans_join", "level == 'master'",
                      ["publication_plan", "individual_plans"], "Магистратура?")
    body += _optional(fl, "gw_bachelor_extra", "gw_bachelor_extra_join", "level == 'bachelor'",
                      ["honors", "gek_payment"], "Бакалавриат?")

    _chain(fl, "start", "distribute_topics", "approve_topics", "ps_setup")
    _chain(fl, "ps_setup", "gak_order", "pj_setup")
    _chain(fl, "ps_setup", "consult_schedule", "seminars", "pj_setup")
    _chain(fl, "ps_setup", "gw_master_plans")
    _chain(fl, "gw_master_plans_join", "pj_setup")
    _chain(fl, "pj_setup", "ps_main")
    _chain(fl, "ps_main", "student_vkr", "pj_main")
    _chain(fl, "ps_main", "defense_schedule", "plagiarism_responsible", "organize_defenses", "gw_bachelor_extra")
    _chain(fl, "gw_bachelor_extra_join", "pj_main")
    _chain(fl, "pj_main", "report_results", "employment", "archive", "end")
    body += _control_point("distribute_topics", CONTROL_POINTS["distribute_topics"], fl)
    body += fl.lines

    header = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- СГЕНЕРИРОВАНО bpmn/tobe/build_tobe.py — не редактировать вручную, править генератор.\n"
        "     To-be модель процесса «Защита ВКР» (T-22): уровень выпуска + многоэкземплярный\n"
        "     подпроцесс по каждому студенту (переменная students — список). level =\n"
        "     'bachelor' | 'master' включает шаги, специфичные для уровня по каталогу.\n"
        "     Дорожки = роли исполнителей. Таблица соответствия каталогу — TRACEABILITY.md.\n"
        "     Переменные запуска: level, students, topics_days, normcontrol_days,\n"
        "     plagiarism_days, admission_days, topic_change_needed, report_2_ok. -->\n"
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"\n'
        '                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '                  id="Defs_vkr_defense_tobe" targetNamespace="http://adaptive-bpm-loop/vkr_defense_tobe">\n'
        '  <bpmn:process id="vkr_defense_tobe" name="Защита ВКР (выпуск), to-be" isExecutable="true">\n'
    )
    inner = "\n".join("    " + line for line in lanes_xml + body)
    return header + inner + "\n  </bpmn:process>\n</bpmn:definitions>\n"


def _refs(prefix: str, nums: list[int]) -> str:
    return ", ".join(f"{prefix}.{n:02d}" for n in nums) or "—"


def build_traceability() -> str:
    lane_name = {lid: name for lid, (name, _) in LANES.items()}
    lines = [
        "# Трассировка «каталог кафедры → to-be модель «Защита ВКР»» (T-22)",
        "",
        "> СГЕНЕРИРОВАНО `bpmn/tobe/build_tobe.py` вместе с `vkr_defense_tobe.bpmn` — таблица и модель",
        "> из одного источника и не расходятся. Источник мероприятий — «Бизнес-процессы кафедры",
        "> САПРиПК (версия 3.0)», таблицы БПБак.ВРБ и БПМаг.МД. **Номера ВРБ.01–24 и МД.01–26 назначены",
        "> по порядку строк каталога**: у шифров в каталоге номеров нет.",
        "",
        "## Структура модели",
        "",
        "- **Уровень выпуска** (процесс `vkr_defense_tobe`): темы, приказы, ГЭК, консультации, график и",
        "  организация защит, отчёт, трудоустройство, архив.",
        "- **Уровень студента** (многоэкземплярный подпроцесс `student_vkr`, по одному экземпляру на",
        "  каждого студента из списка `students`): отчёты, изменение темы, выговор, нормоконтроль,",
        "  заимствования, отзыв и рецензия, допуск, защита, протоколы.",
        "- **Развилки по уровню подготовки** (`level`): шаги, которые в каталоге есть только у одного уровня.",
        "- **Контрольные точки** (необрывающий таймер → эскалация завкафедрой): "
        + ", ".join(f"`{t}` (`{v}`)" for t, v in CONTROL_POINTS.items()) + ".",
        "- **Дорожки = роли**: " + "; ".join(
            f"«{name}» → `{role}`" if role else f"«{name}» → роли в системе пока нет"
            for name, role in LANES.values()
        ) + ".",
        "",
    ]

    def section(title: str, catalog: dict, prefix: str, idx: int) -> None:
        lines.extend([f"## {title}", "",
                      "| № | Мероприятие каталога | Срок по каталогу | Элемент модели | Дорожка | Уровень в модели |",
                      "|---|---|---|---|---|---|"])
        for num, (name, due) in catalog.items():
            hits = [tid for tid, row in TASKS.items() if num in row[idx]]
            elems = "<br>".join(f"`{t}` — {TASKS[t][0]}" for t in hits) or "**не смоделировано**"
            lanes = "<br>".join(sorted({lane_name[TASKS[t][1]] for t in hits})) or "—"
            levels = "<br>".join(sorted({TASKS[t][4] for t in hits})) or "—"
            lines.append(f"| {prefix}.{num:02d} | {name} | {due} | {elems} | {lanes} | {levels} |")
        lines.append("")

    section("Бакалавриат (БПБак.ВРБ)", VRB, "ВРБ", 2)
    section("Магистратура (БПМаг.МД)", MD, "МД", 3)

    lines.extend(["## Обратная трассировка: элемент модели → каталог", "",
                  "| Элемент модели | Уровень процесса | Дорожка | ВРБ | МД | Рабочая модель `vkr_defense` | Примечание |",
                  "|---|---|---|---|---|---|---|"])
    for tid, (name, lane, vrb, md, _level, working) in TASKS.items():
        where = "студент" if tid in STUDENT_TASKS else "выпуск"
        lines.append(
            f"| `{tid}` — {name} | {where} | {lane_name[lane]} | {_refs('ВРБ', vrb)} | {_refs('МД', md)} | "
            f"{f'`{working}`' if working else '—'} | {NOTES.get(tid, '')} |"
        )
    lines.extend([
        "",
        "## Отличия to-be модели от рабочей модели `vkr_defense`",
        "",
        "- Рабочая модель — 7 шагов (`approve_topics`, `report_2`, `publish_for_normcontrol`, `normcontrol`, "
        "`publish_final`, `admission_order`, `defense`) на одного студента, со студентом как участником "
        "(дорожка «Студент», экран «Моя защита»); to-be — 29 шагов на выпуск с подпроцессом по студентам. "
        "Один экземпляр = один студент — это нужно для анализа журнала событий: case = траектория студента.",
        "- В рабочей модели у предзащиты нет ветки «не прошёл → выговор», а контрольных точек с таймерами — 3 "
        "(`approve_topics`, `publish_for_normcontrol`, `normcontrol`).",
        "- Эскалация в рабочей модели **прерывающая** (экземпляр завершается), в to-be — **необрывающая**: "
        "завкафедрой уведомляется, шаг продолжается. Прерывание в рабочей модели — упрощение ради "
        "измеримости эксперимента (глава 4), а не утверждение о реальном процессе.",
        "- Календарные сроки каталога (месяцы, «за N дней до защиты») в to-be остаются в этой таблице; "
        "таймерами смоделированы только 4 контрольные точки. Абсолютных дат (заседание ГЭК) система "
        "не моделирует — то же ограничение, что описано в `experiment/params.py`.",
        "- To-be исполняется оркестратором (`python -m orchestrator.tobe_smoke_test`), но в реестр "
        "ручного запуска не добавлена: в подпроцессе несколько READY-задач с одним именем "
        "(по одной на студента), а REST адресует задачу по имени — для запуска через UI нужна "
        "адресация по экземпляру задачи.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    (OUT_DIR / "vkr_defense_tobe.bpmn").write_text(build_bpmn(), encoding="utf-8")
    (OUT_DIR / "TRACEABILITY.md").write_text(build_traceability(), encoding="utf-8")
    print(f"written: {OUT_DIR / 'vkr_defense_tobe.bpmn'}")
    print(f"written: {OUT_DIR / 'TRACEABILITY.md'}")


if __name__ == "__main__":
    main()

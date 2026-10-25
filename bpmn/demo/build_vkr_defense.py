"""Генератор рабочих моделей «Защита ВКР»: vkr_defense.bpmn и vkr_defense_fast.bpmn.

Обе модели обязаны совпадать во всём, кроме единицы таймеров (дни у боевой,
минуты у тестовой) — поэтому они строятся из одного описания, а не
редактируются руками по отдельности.

Рабочая модель — подмножество to-be модели (bpmn/tobe/): один экземпляр =
защита одного студента (для анализа журнала экземпляр должен описывать путь
одного человека; в to-be экземпляр — весь выпуск). Идентификаторы шагов
совпадают с to-be, поэтому bpmn/tobe/TRACEABILITY.md остаётся верной.

Структурная адаптация (E15): build(process_id, added_checkpoints) собирает
версию модели, в которой на перечисленные шаги без срока поставлены
контрольные точки (напоминание + эскалация, как у остальных относительных
точек). Её вызывает agents/model_store.py, когда завкафедрой принимает
корректировку add_checkpoint; файлы в этой папке — базовая версия (без
добавленных точек).

Запуск: python bpmn/demo/build_vkr_defense.py  (из корня adaptive-bpm-loop)
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT_DIR.parent.parent))  # корень adaptive-bpm-loop — для импорта mining

from mining.control_points import UNSET_DATE, VKR_DEFENSE_DATE_POINTS, added_control_point  # noqa: E402

DATE_POINTS = {p.task: p for p in VKR_DEFENSE_DATE_POINTS}

# Порядок шагов = порядок в процессе. (id, название, дорожка, контрольная точка)
# Контрольная точка: (имя активности-напоминания, имя активности-эскалации).
STEPS = [
    ("approve_topics", "Утверждение тем ВКР", "Секретарь кафедры", ("remind_topics", "escalate_topics")),
    ("report_2", "Предзащита", "Руководитель ВКР", None),
    ("publish_for_normcontrol", "Публикация ПЗ и ТЗ в Moodle для нормоконтроля", "Студент",
     ("remind_publish", "escalate_publish")),
    ("normcontrol", "Нормоконтроль", "Нормоконтролёр", ("remind_normcontrol", "escalate_normcontrol")),
    ("publish_final", "Публикация финальных версий в Moodle", "Студент", None),
    # E15: шаг каталога без срока в регламенте (МД.19 — «параллельно с проверкой
    # на плагиат»). Срока у него нет, пока анализ не покажет, что он нужен.
    ("supervisor_review", "Отзыв руководителя и рецензия", "Руководитель ВКР", None),
    ("admission_order", "Приказ о допуске к защите", "Секретарь кафедры", None),
    ("defense", "Защита ВКР", "Секретарь кафедры", None),
]

VARIANTS = {
    "vkr_defense": {"unit": "D", "prefix": "P", "suffix": "", "unit_name": "ДНЯХ"},
    "vkr_defense_fast": {"unit": "M", "prefix": "PT", "suffix": " (тест)", "unit_name": "МИНУТАХ"},
}

LANE_IDS = {
    "Секретарь кафедры": "lane_secretary",
    "Руководитель ВКР": "lane_supervisor",
    "Студент": "lane_student",
    "Нормоконтролёр": "lane_normcontrol",
}


def _x(s: str) -> str:
    return escape(s, {'"': "&quot;"})


def checkpointable(step_id: str) -> bool:
    """Можно ли добавить контрольную точку: шаг есть в модели и срока у него нет."""
    return any(sid == step_id and cp is None for sid, _n, _l, cp in STEPS) and step_id not in DATE_POINTS


def build(process_id: str, added_checkpoints: tuple[str, ...] = ()) -> str:
    v = VARIANTS[process_id]
    for step_id in added_checkpoints:
        if not checkpointable(step_id):
            raise ValueError(f"на шаг {step_id!r} нельзя добавить контрольную точку: его нет или срок уже есть")
    added = {}
    for step_id in added_checkpoints:
        cp = added_control_point(step_id)
        added[step_id] = (cp.reminder_activity, cp.escalation_activity)
    lines: list[str] = []
    n = 0

    def flow(a: str, b: str) -> None:
        nonlocal n
        n += 1
        lines.append(f'<bpmn:sequenceFlow id="f{n}" sourceRef="{a}" targetRef="{b}"/>')

    lanes: dict[str, list[str]] = {}
    for step_id, _, lane, _cp in STEPS:
        lanes.setdefault(lane, []).append(step_id)
    lines.append('<bpmn:laneSet id="lanes">')
    for lane, refs in lanes.items():
        refs_xml = "".join(f"<bpmn:flowNodeRef>{r}</bpmn:flowNodeRef>" for r in refs)
        lines.append(f'  <bpmn:lane id="{LANE_IDS[lane]}" name="{_x(lane)}">{refs_xml}</bpmn:lane>')
    lines.append("</bpmn:laneSet>")

    lines.append('<bpmn:startEvent id="start"/>')
    previous = "start"
    for step_id, name, _lane, cp in STEPS:
        lines.append(f'<bpmn:userTask id="{step_id}" name="{_x(name + v["suffix"])}"/>')
        flow(previous, step_id)
        previous = step_id
        cp = cp or added.get(step_id)
        if cp is None:
            continue
        remind, escalate = cp
        for activity, variable, cancel, label in (
            (remind, "reminder_days", "false", "Напоминание"),
            (escalate, "escalation_days", "true", "Эскалация"),
        ):
            lines += [
                f'<bpmn:boundaryEvent id="{activity}_timer" attachedToRef="{step_id}" cancelActivity="{cancel}">',
                "  <bpmn:timerEventDefinition>",
                f"    <bpmn:timeDuration xsi:type=\"bpmn:tFormalExpression\">f'{v['prefix']}{{{variable}}}{v['unit']}'"
                "</bpmn:timeDuration>",
                "  </bpmn:timerEventDefinition>",
                "</bpmn:boundaryEvent>",
                f'<bpmn:scriptTask id="{activity}" name="{_x(label)}: {_x(name)}">'
                f"<bpmn:script>{activity}_done = True</bpmn:script></bpmn:scriptTask>",
                f'<bpmn:endEvent id="end_{activity}"/>',
            ]
            flow(f"{activity}_timer", activity)
            flow(activity, f"end_{activity}")
    for step_id, name, _lane, _cp in STEPS:
        point = DATE_POINTS.get(step_id)
        if point is None:
            continue
        # Срок от календарной даты (E14): момент лежит в данных экземпляра,
        # его считает api/milestones.py; нет даты — UNSET_DATE, таймер не наступит.
        # Обе эскалации необрывающие: шаг продолжается, завкафедрой уведомлён.
        for activity, field, label in (
            (point.reminder_activity, point.remind_field, "Напоминание"),
            (point.escalation_activity, point.due_field, "Срок истёк"),
        ):
            lines += [
                f'<bpmn:boundaryEvent id="{activity}_timer" attachedToRef="{step_id}" cancelActivity="false">',
                "  <bpmn:timerEventDefinition>",
                f"    <bpmn:timeDate xsi:type=\"bpmn:tFormalExpression\">globals().get('{field}', '{UNSET_DATE}')"
                "</bpmn:timeDate>",
                "  </bpmn:timerEventDefinition>",
                "</bpmn:boundaryEvent>",
                f'<bpmn:scriptTask id="{activity}" name="{_x(label)}: {_x(name)}">'
                f"<bpmn:script>{activity}_done = True</bpmn:script></bpmn:scriptTask>",
                f'<bpmn:endEvent id="end_{activity}"/>',
            ]
            flow(f"{activity}_timer", activity)
            flow(activity, f"end_{activity}")
    lines.append('<bpmn:endEvent id="end_main"/>')
    flow(previous, "end_main")

    steps_doc = "\n".join(
        f"       {sid:<24} {name} — {lane}{' [контрольная точка]' if cp else ''}"
        f"{' [контрольная точка добавлена корректировкой]' if sid in added else ''}"
        f"{' [срок от даты]' if sid in DATE_POINTS else ''}"
        for sid, name, lane, cp in STEPS
    )
    version_doc = (
        f"\n     Версия со структурной адаптацией: добавлены контрольные точки на {', '.join(added_checkpoints)}."
        if added_checkpoints else ""
    )
    header = f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- СГЕНЕРИРОВАНО bpmn/demo/build_vkr_defense.py — не редактировать вручную.
     Рабочая модель «Защита ВКР» ({process_id}): защита одного студента.{version_doc} Таймеры
     в {v["unit_name"]} (reminder_days/escalation_days передаются через
     Orchestrator.start_instance(initial_data=...); дефолтов в выражениях нет —
     забытый параметр должен падать, а не тихо брать случайное значение).
     Напоминание не прерывает шаг; эскалация прерывающая и завершает экземпляр —
     упрощение рабочей модели для измеримости (в to-be эскалация необрывающая).
     Шаги:
{steps_doc}
     [срок от даты] — таймеры timeDate от дат предзащиты/защиты конкретного
     студента (mining.control_points.VKR_DEFENSE_DATE_POINTS, считает
     api/milestones.py): эскалация необрывающая, в контур адаптации не входят. -->
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                  id="Defs_{process_id}" targetNamespace="http://adaptive-bpm-loop/{process_id}">
  <bpmn:process id="{process_id}" isExecutable="true">
'''
    return header + "\n".join("    " + line for line in lines) + "\n  </bpmn:process>\n</bpmn:definitions>\n"


def main() -> None:
    for process_id in VARIANTS:
        path = OUT_DIR / f"{process_id}.bpmn"
        path.write_text(build(process_id), encoding="utf-8")
        print(f"written: {path}")


if __name__ == "__main__":
    main()

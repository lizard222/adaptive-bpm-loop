"""Кто может видеть и выполнять READY-задачу (роли на сервере, часть T-25).

Роль исполнителя шага задаётся дорожкой (lane) BPMN-модели, а не отдельным
справочником в коде: SpiffWorkflow кладёт имя дорожки в task_spec.lane.
Здесь только соответствие "имя дорожки -> роли пользователей" (роли — из
api/auth.py::ROLES). admin — суперпользователь, видит и выполняет всё.

Шаг без дорожки (старые демо-/экспериментальные модели смоук-тестов, где
дорожек нет) доступен только admin: раньше такие задачи видел любой
пользователь, теперь нет — это и есть смысл серверной проверки.

Дорожку берём из ТЕКУЩЕЙ модели реестра (orchestrator/process_registry.py)
по имени шага, а не из сериализованного состояния экземпляра: экземпляры,
запущенные до появления дорожек в BPMN, хранят старую копию модели без них и
иначе навсегда остались бы доступны только admin. Сериализованная дорожка —
запасной вариант для процессов вне реестра.
"""
from __future__ import annotations

from functools import lru_cache

from orchestrator.process_registry import PROCESS_REGISTRY
from orchestrator.specs import load_spec_with_subprocesses

SUPERUSER_ROLE = "admin"
STUDENT_LANE = "Студент"

# Совпадает с дорожками to-be модели (bpmn/tobe/build_tobe.py::LANES). В рабочей
# модели vkr_defense дорожек только две — секретарь и нормоконтролёр.
# «ГЭК» и «Ответственный за проверку на заимствования» ролей в системе пока не
# имеют — их шаги доступны только admin.
LANE_ROLES: dict[str, frozenset[str]] = {
    "Секретарь кафедры": frozenset({"secretary"}),
    "Нормоконтролёр": frozenset({"normcontrol"}),
    "Заведующий кафедрой": frozenset({"dept_head"}),
    "Руководитель ВКР": frozenset({"supervisor"}),
    "Студент": frozenset({"student"}),
}


@lru_cache(maxsize=None)
def _registry_lanes(process_key: str) -> dict[str, str | None]:
    reg = PROCESS_REGISTRY.get(process_key)
    if reg is None:
        return {}
    spec, subprocess_specs = load_spec_with_subprocesses(reg.bpmn_file, reg.process_id)
    lanes: dict[str, str | None] = {}
    for sp in (spec, *subprocess_specs.values()):  # шаги внутри подпроцессов тоже
        lanes.update({name: task_spec.lane for name, task_spec in sp.task_specs.items()})
    return lanes


def resolve_lane(process_key: str, task_name: str, serialized_lane: str | None = None) -> str | None:
    return _registry_lanes(process_key).get(task_name) or serialized_lane


def can_act(role: str, lane: str | None, username: str | None = None, case_student: str | None = None) -> bool:
    """Шаг дорожки «Студент» — только студенту, привязанному к ЭТОМУ
    экземпляру (api/participants.py), а не любому пользователю с ролью
    student: иначе каждый студент видел бы и мог выполнить шаги чужих защит."""
    if role == SUPERUSER_ROLE:
        return True
    if lane is None or role not in LANE_ROLES.get(lane, frozenset()):
        return False
    if lane == STUDENT_LANE:
        return case_student is not None and username == case_student
    return True

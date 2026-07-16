"""Рендер документов из шаблонов кафедры (E1/T-36, ФТ-С-8.1).

TEMPLATES — реестр доступных шаблонов: имя -> файл + обязательные поля.
Сейчас один плейсхолдер-шаблон (build_placeholder_template.py) — реальные
формы кафедры подставляются заменой файла и записи в TEMPLATES, без
изменения кода рендера или агента (agents/templater_agent.py).

render() проверяет обязательные поля и бросает MissingFieldsError, если
чего-то не хватает — ЭТО ЖЕ ПРАВИЛО (ФТ-А-Ш-2: отказ, а не неполный
документ) продублировано агентом на уровне FIPA-протокола (refuse до
формирования), но проверка здесь — защита и для прямого вызова в обход
агента (например, из будущего REST-эндпоинта, T-37).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from docxtpl import DocxTemplate


class MissingFieldsError(Exception):
    def __init__(self, missing: list[str]):
        super().__init__(f"отсутствуют обязательные поля: {', '.join(missing)}")
        self.missing = missing


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    path: Path
    required_fields: tuple[str, ...]


TEMPLATES: dict[str, TemplateSpec] = {
    "vkr_admission_order": TemplateSpec(
        name="vkr_admission_order",
        path=Path(__file__).parent / "vkr_admission_order.docx",
        required_fields=(
            "order_number", "order_date", "student_name", "topic", "supervisor_name", "defense_date",
        ),
    ),
}


def missing_fields(spec: TemplateSpec, context: dict) -> list[str]:
    return [f for f in spec.required_fields if not context.get(f)]


def render(spec: TemplateSpec, context: dict, out_dir: Path) -> Path:
    missing = missing_fields(spec, context)
    if missing:
        raise MissingFieldsError(missing)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = DocxTemplate(spec.path)
    doc.render(context)
    out_path = out_dir / f"{spec.name}_{uuid.uuid4().hex[:8]}.docx"
    doc.save(out_path)
    return out_path

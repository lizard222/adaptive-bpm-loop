"""Загрузка BPMN-моделей в спецификации SpiffWorkflow (ФТ-С-1.1).

На Windows штатный BpmnParser.add_bpmn_file() падает на кириллице (пытается
читать файл в системной кодировке cp1251) — находка спайка T-28. Грузим XML
через lxml.
"""
from pathlib import Path

from lxml import etree
from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser
from SpiffWorkflow.bpmn.parser.util import full_tag


def load_spec(bpmn_file: Path, process_id: str | None = None):
    """Возвращает WorkflowSpec для процесса из файла BPMN.

    Если process_id не указан, берётся первый исполняемый процесс в файле
    (isExecutable="true") — удобно для однопроцессных файлов моделей.
    """
    parser = BpmnParser()
    tree = etree.parse(str(bpmn_file))
    parser.add_bpmn_xml(tree, filename=str(bpmn_file))

    if process_id is None:
        root = tree.getroot()
        for proc in root.iter(full_tag("process")):
            if proc.get("isExecutable") == "true":
                process_id = proc.get("id")
                break
        if process_id is None:
            raise ValueError(f"В {bpmn_file} не найден исполняемый процесс (isExecutable=true)")

    return parser.get_spec(process_id)

# -*- coding: utf-8 -*-
"""Сквозной смоук-тест агента Шаблонизатор (E1/T-36) на реальной инфраструктуре.

Первый агент в прототипе, полностью использующий FIPA Request Interaction
Protocol (request -> agree -> inform-done/failure, либо сразу refuse) — до
этого агенты использовали propose/accept-proposal/reject-proposal (T-42)
или простой inform (T-33/T-34).

Три сценария:
  1. Полный контекст -> agree, затем inform-done с путём к РЕАЛЬНОМУ .docx —
     файл действительно существует, поля подставлены, тегов {{ }} не осталось,
     событие "document_generated" реально записано в event_log (ФТ-С-8.2).
  2. Неполный контекст -> сразу refuse (без agree!) с точным списком
     недостающих полей — ни один файл не создан (ФТ-А-Ш-2: никогда не
     формировать неполный документ).
  3. Неизвестный шаблон -> refuse с соответствующей причиной.

Запуск: python -m agents.templater_smoke_test
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

from .xmpp_dev import enable_unencrypted_plain_auth

enable_unencrypted_plain_auth()

import psycopg  # noqa: E402
import spade  # noqa: E402
from docx import Document  # noqa: E402
from spade.agent import Agent  # noqa: E402
from spade.behaviour import OneShotBehaviour  # noqa: E402
from spade.message import Message  # noqa: E402

from api.config import settings  # noqa: E402

from .templater_agent import TemplaterAgent  # noqa: E402

RUN_ID = uuid.uuid4().hex[:6]
PASSWORD = "smoke-password"
OUTPUT_DIR = Path(__file__).parents[1] / "spikes" / "_scratch" / "templater_smoke"


class ProcessAgentStub(Agent):
    """Заглушка "агента процесса" — шлёт request Шаблонизатору и собирает ответы."""

    class SendRequest(OneShotBehaviour):
        def __init__(self, to_jid: str, template: str, context: dict, case_id: str | None, process_key: str | None):
            super().__init__()
            self.to_jid = to_jid
            self.template_name = template
            self.context = context
            self.case_id = case_id
            self.process_key = process_key
            self.replies: list[Message] = []

        async def run(self):
            msg = Message(to=self.to_jid)
            msg.set_metadata("performative", "request")
            msg.set_metadata("template", self.template_name)
            if self.case_id:
                msg.set_metadata("case_id", self.case_id)
            if self.process_key:
                msg.set_metadata("process_key", self.process_key)
            msg.thread = uuid.uuid4().hex
            msg.body = json.dumps(self.context, ensure_ascii=False)
            await self.send(msg)

            for _ in range(2):  # agree + inform-done/failure, либо один refuse
                reply = await self.receive(timeout=8)
                if reply is None:
                    break
                self.replies.append(reply)
                if reply.get_metadata("performative") in ("refuse", "inform-done", "failure"):
                    break

    async def setup(self):
        pass


def _event_exists(case_id: str) -> bool:
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute(
            "SELECT count(*) FROM event_log WHERE case_id=%s AND activity='document_generated'",
            (case_id,),
        ).fetchone()
    return row[0] > 0


async def main() -> int:
    checks: list[bool] = []

    def check(label: str, cond: bool) -> None:
        checks.append(bool(cond))
        print(("PASS  " if cond else "FAIL  ") + label)

    templater_jid = f"smoke-templater-{RUN_ID}@localhost"
    templater = TemplaterAgent(templater_jid, PASSWORD, settings.database_url, OUTPUT_DIR)
    await templater.start(auto_register=True)

    stub_jid = f"smoke-procstub-{RUN_ID}@localhost"
    stub = ProcessAgentStub(stub_jid, PASSWORD)
    await stub.start(auto_register=True)

    # --- Сценарий 1: полный контекст ---
    case_id_1 = f"vkr-{RUN_ID}-0001"
    full_ctx = {
        "order_number": "12-у", "order_date": "01.02.2027", "student_name": "Иванов И.И.",
        "topic": "Адаптивное управление бизнес-процессами вуза", "supervisor_name": "Петров П.П.",
        "defense_date": "15.06.2027",
    }
    beh1 = stub.SendRequest(templater_jid, "vkr_admission_order", full_ctx, case_id_1, "vkr_defense_demo")
    stub.add_behaviour(beh1)
    await beh1.join()

    performatives_1 = [r.get_metadata("performative") for r in beh1.replies]
    check("сценарий 1: получены agree и inform-done по порядку", performatives_1 == ["agree", "inform-done"])

    if performatives_1 == ["agree", "inform-done"]:
        out_path = Path(beh1.replies[1].body)
        check("сценарий 1: файл реально существует", out_path.exists())
        doc = Document(str(out_path))
        text = "\n".join(p.text for p in doc.paragraphs)
        check("сценарий 1: поле реально подставлено", "Иванов И.И." in text)
        check("сценарий 1: незаполненных тегов не осталось", "{{" not in text)
    else:
        check("сценарий 1: файл реально существует", False)
        check("сценарий 1: поле реально подставлено", False)
        check("сценарий 1: незаполненных тегов не осталось", False)

    check("сценарий 1: факт формирования записан в event_log (ФТ-С-8.2)", _event_exists(case_id_1))

    # --- Сценарий 2: неполный контекст ---
    case_id_2 = f"vkr-{RUN_ID}-0002"
    beh2 = stub.SendRequest(templater_jid, "vkr_admission_order", {"order_number": "13-у"}, case_id_2, "vkr_defense_demo")
    stub.add_behaviour(beh2)
    await beh2.join()

    performatives_2 = [r.get_metadata("performative") for r in beh2.replies]
    check("сценарий 2: сразу refuse, БЕЗ agree (не начинает работу над неполным запросом)",
          performatives_2 == ["refuse"])
    if performatives_2 == ["refuse"]:
        missing = json.loads(beh2.replies[0].body).get("missing_fields", [])
        expected_missing = {"order_date", "student_name", "topic", "supervisor_name", "defense_date"}
        check("сценарий 2: перечислены именно недостающие поля", set(missing) == expected_missing)
    else:
        check("сценарий 2: перечислены именно недостающие поля", False)
    check("сценарий 2: событие в журнал не писалось (документ не сформирован)", not _event_exists(case_id_2))

    # --- Сценарий 3: неизвестный шаблон ---
    beh3 = stub.SendRequest(templater_jid, "no_such_template", {}, None, None)
    stub.add_behaviour(beh3)
    await beh3.join()
    check("сценарий 3: refuse на неизвестный шаблон",
          len(beh3.replies) == 1 and beh3.replies[0].get_metadata("performative") == "refuse"
          and beh3.replies[0].get_metadata("reason") == "unknown_template")

    await templater.stop()
    await stub.stop()

    print(f"\nИтого: {sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(spade.run(main()))

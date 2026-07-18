"""Агент Шаблонизатор (T-36, ФТ-А-Ш-1..3, ФТ-С-8).

Формирует документы (.docx) из шаблонов кафедры по данным экземпляра
процесса (templates/render.py). Синтетический плейсхолдер-шаблон
(templates/vkr_admission_order.docx) вместо реальных форм кафедры — они
запрошены (T-02), не подтверждены; замена файла шаблона не требует менять
код агента (реестр TEMPLATES в templates/render.py не завязан на конкретные
имена полей внутри самого агента).

Протокол — FIPA Request Interaction Protocol, задействован полностью
впервые в прототипе (остальные агенты использовали propose/accept-proposal
или голый inform): request -> agree (запрос принят к исполнению) ->
inform-done (путь к файлу) при успехе, либо вместо agree сразу refuse
(запрошен неизвестный шаблон, ИЛИ не хватает обязательных полей — ФТ-А-Ш-2:
принципиальный запрет формировать НЕПОЛНЫЙ документ), либо после agree —
failure при непредвиденной ошибке рендера (NFR-4).

Stateless (ФТ-А-Ш-3): поведение не хранит между запросами ничего, кроме
статичного реестра шаблонов, общего для всех запросов.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import psycopg
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

from eventlog.documents import log_document_generated
from templates.render import TEMPLATES, MissingFieldsError, missing_fields, render

logger = logging.getLogger("agents.templater")


class TemplaterAgent(Agent):
    def __init__(self, jid: str, password: str, database_url: str, output_dir: Path):
        super().__init__(jid, password)
        self.database_url = database_url
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.generated: list[Path] = []  # для наблюдения из тестов

    async def setup(self) -> None:
        self.add_behaviour(self.Serve())

    def _log_generated(self, case_id: str, process_key: str, template_name: str, out_path: Path) -> None:
        with psycopg.connect(self.database_url) as conn:
            log_document_generated(conn, case_id, process_key, template_name, out_path, resource="templater")
            conn.commit()

    class Serve(CyclicBehaviour):
        async def run(self) -> None:
            msg = await self.receive(timeout=5)
            if msg is None or msg.get_metadata("performative") != "request":
                return
            agent: TemplaterAgent = self.agent

            template_name = msg.get_metadata("template")
            reply = Message(to=str(msg.sender))
            reply.thread = msg.thread

            spec = TEMPLATES.get(template_name)
            if spec is None:
                reply.set_metadata("performative", "refuse")
                reply.set_metadata("reason", "unknown_template")
                reply.body = f"неизвестный шаблон: {template_name!r}"
                await self.send(reply)
                return

            context = json.loads(msg.body) if msg.body else {}
            missing = missing_fields(spec, context)
            if missing:
                reply.set_metadata("performative", "refuse")
                reply.set_metadata("reason", "missing_fields")
                reply.body = json.dumps({"missing_fields": missing}, ensure_ascii=False)
                await self.send(reply)
                return

            agree = Message(to=str(msg.sender))
            agree.thread = msg.thread
            agree.set_metadata("performative", "agree")
            await self.send(agree)

            done = Message(to=str(msg.sender))
            done.thread = msg.thread
            try:
                out_path = render(spec, context, agent.output_dir)
            except MissingFieldsError as exc:  # защита на случай гонки — не должно случиться после проверки выше
                done.set_metadata("performative", "failure")
                done.body = str(exc)
                await self.send(done)
                return
            except Exception as exc:  # noqa: BLE001 — NFR-4: любая иная ошибка рендера -> failure, не тишина
                logger.exception("Ошибка рендера шаблона %s", template_name)
                done.set_metadata("performative", "failure")
                done.body = f"ошибка рендера: {exc}"
                await self.send(done)
                return

            agent.generated.append(out_path)
            case_id = msg.get_metadata("case_id")
            process_key = msg.get_metadata("process_key")
            if case_id and process_key:
                agent._log_generated(case_id, process_key, template_name, out_path)  # ФТ-С-8.2

            done.set_metadata("performative", "inform-done")
            done.body = str(out_path)
            await self.send(done)

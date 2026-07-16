"""Агент Аналитик-Адаптер (T-42, ФТ-А-А-1..5).

Замыкает контур адаптации: по завершении цикла запускает конвейер анализа
(T-40, mining/conveyor.py) и алгоритм классификации расхождений (T-41,
mining/corrections.py), предъявляет предложения уполномоченному пользователю
(FIPA propose, ФТ-С-7.4) и, после подтверждения, фиксирует новую версию
параметров процесса, уведомляя Планировщика и Контролера (ФТ-А-А-4).

Триггер "цикл завершился" в v1 — внешний (вызов process_cycle извне: из
эксперимента T-51 или вручную), а не автономное поведение агента: детектор
границы цикла — отдельная задача, не входящая в объём T-42.

Режим применения (ФТ-С-7.6):
  - "propose" (по умолчанию) — ждёт accept-proposal/reject-proposal на каждую
    корректировку (по одному FIPA-сообщению с уникальным thread), применяет
    только принятые;
  - "auto" — применяет все предложенные корректировки немедленно, без
    подтверждения; для имитационного эксперимента, где эмулировать решение
    человека не нужно.

Хранилище версий: applied_corrections (T-42) — журнал ИСТОРИИ применённых
корректировок; process_params_current (E3) — СОСТОЯНИЕ, одна строка на
процесс с параметрами, действующими прямо сейчас. Оба обновляются здесь при
применении корректировок (agents/params_store.py — переиспользует тот же
маппинг «корректировка → параметр», что уже проверен в offline-эксперименте,
experiment/params.apply_corrections). Планировщик (T-33) реально читает
process_params_current перед каждым запуском экземпляра — контур адаптации
теперь замкнут и в живой системе, не только в эксперименте (E3 закрывает
пробел, найденный при подготовке фазы E). Контролер пока только принимает
уведомление (см. agents/controller_agent.py) — динамическое добавление
новых контрольных точек из add_checkpoint корректировок не реализовано,
задокументировано отдельно.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour
from spade.message import Message

from experiment.params import ProcessParams
from mining.control_points import ControlPoint
from mining.conveyor import ConveyorReport, analyze_cycle
from mining.corrections import Correction, Thresholds, propose_corrections

from .params_store import apply_and_store


@dataclass
class CycleAnalysisResult:
    process_key: str
    report: ConveyorReport
    proposed: list[Correction] = field(default_factory=list)
    accepted: list[Correction] = field(default_factory=list)
    rejected: list[Correction] = field(default_factory=list)
    version: int | None = None


class AnalystAdapterAgent(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        database_url: str,
        recipient_jid: str,                     # уполномоченный человек (завкафедрой) — FIPA propose
        notify_jids: list[str] | None = None,   # Планировщик/Контролер — FIPA inform о новой версии
        thresholds: Thresholds = Thresholds(),
        decision_timeout: float = 10.0,
        default_params: ProcessParams = ProcessParams(reminder_days=7, escalation_days=14),
    ):
        super().__init__(jid, password)
        self.database_url = database_url
        self.recipient_jid = recipient_jid
        self.notify_jids = notify_jids or []
        self.thresholds = thresholds
        self.decision_timeout = decision_timeout
        self.default_params = default_params
        self.last_result: CycleAnalysisResult | None = None  # для наблюдения из тестов

    async def setup(self) -> None:
        pass  # автономных поведений нет — см. докстринг модуля про внешний триггер

    async def process_cycle(
        self,
        process_key: str,
        bpmn_file: Path,
        control_points: list[ControlPoint],
        case_ids: list[str] | None = None,
        mode: str = "propose",
    ) -> CycleAnalysisResult:
        """Запускает анализ цикла как SPADE-поведение (отправка/приём сообщений
        доступны только внутри Behaviour) и дожидается его завершения."""
        behaviour = _ProcessCycleBehaviour(process_key, bpmn_file, control_points, case_ids, mode)
        self.add_behaviour(behaviour)
        await behaviour.join()
        self.last_result = behaviour.result
        return behaviour.result

    # ---------- персистентность (вызывается из behaviour) ----------

    def save_report(self, process_key: str, report: ConveyorReport, corrections: list[Correction]) -> None:
        with psycopg.connect(self.database_url) as conn:
            conn.execute(
                "INSERT INTO analysis_reports (process_key, n_cases, fitness, precision_, report, corrections) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    process_key, report.n_cases, report.fitness, report.precision,
                    psycopg.types.json.Json(report.to_dict()),
                    psycopg.types.json.Json([c.to_dict() for c in corrections]),
                ),
            )
            conn.commit()

    def apply_corrections(
        self, process_key: str, accepted: list[Correction], mode: str,
    ) -> tuple[int, ProcessParams]:
        with psycopg.connect(self.database_url) as conn:
            version = conn.execute(
                "SELECT coalesce(max(version), 0) + 1 FROM applied_corrections WHERE process_key = %s",
                (process_key,),
            ).fetchone()[0]
            for c in accepted:
                conn.execute(
                    "INSERT INTO applied_corrections "
                    "(process_key, version, kind, target, mode, evidence, justification) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (process_key, version, c.kind, c.target, mode,
                     psycopg.types.json.Json(c.evidence), c.justification),
                )
            conn.commit()
        # process_params_current (E3) — состояние, реально читаемое Планировщиком;
        # тот же маппинг «корректировка -> параметр», что и в эксперименте.
        updated_params = apply_and_store(self.database_url, process_key, self.default_params, accepted, version)
        return version, updated_params


class _ProcessCycleBehaviour(OneShotBehaviour):
    def __init__(
        self,
        process_key: str,
        bpmn_file: Path,
        control_points: list[ControlPoint],
        case_ids: list[str] | None,
        mode: str,
    ):
        super().__init__()
        self.process_key = process_key
        self.bpmn_file = bpmn_file
        self.control_points = control_points
        self.case_ids = case_ids
        self.mode = mode
        self.result: CycleAnalysisResult | None = None

    async def run(self) -> None:
        agent: AnalystAdapterAgent = self.agent

        report = analyze_cycle(agent.database_url, self.process_key, self.bpmn_file,
                                self.control_points, self.case_ids)
        corrections = propose_corrections(report, agent.thresholds)
        agent.save_report(self.process_key, report, corrections)

        if not corrections:
            accepted: list[Correction] = []
        elif self.mode == "auto":
            accepted = list(corrections)
        else:
            accepted = await self._propose_and_collect(corrections)

        rejected = [c for c in corrections if c not in accepted]

        version = None
        if accepted:
            version, updated_params = agent.apply_corrections(self.process_key, accepted, self.mode)
            await self._notify_new_version(version, accepted, updated_params)

        self.result = CycleAnalysisResult(
            process_key=self.process_key, report=report, proposed=corrections,
            accepted=accepted, rejected=rejected, version=version,
        )

    async def _propose_and_collect(self, corrections: list[Correction]) -> list[Correction]:
        agent: AnalystAdapterAgent = self.agent
        pending: dict[str, Correction] = {}
        for c in corrections:
            thread = uuid.uuid4().hex
            pending[thread] = c
            msg = Message(to=agent.recipient_jid)
            msg.set_metadata("performative", "propose")
            msg.set_metadata("process_key", self.process_key)
            msg.set_metadata("kind", c.kind)
            msg.set_metadata("target", c.target)
            msg.thread = thread
            msg.body = c.justification
            await self.send(msg)

        accepted: list[Correction] = []
        start = time.monotonic()
        while pending:
            remaining = agent.decision_timeout - (time.monotonic() - start)
            if remaining <= 0:
                break
            reply = await self.receive(timeout=remaining)
            if reply is None:
                break
            corr = pending.pop(reply.thread, None)
            if corr is None:
                continue  # чужой/просроченный thread
            if reply.get_metadata("performative") == "accept-proposal":
                accepted.append(corr)
        return accepted

    async def _notify_new_version(self, version: int, accepted: list[Correction], updated_params: ProcessParams) -> None:
        agent: AnalystAdapterAgent = self.agent
        summary = ", ".join(f"{c.kind}({c.target})" for c in accepted)
        for jid in agent.notify_jids:
            msg = Message(to=jid)
            msg.set_metadata("performative", "inform")
            msg.set_metadata("event", "process_params_updated")
            msg.set_metadata("process_key", self.process_key)
            msg.set_metadata("version", str(version))
            # Получатель НЕ обязан доверять телу сообщения — он перечитывает
            # process_params_current из БД сам (пуш — это триггер "проснись
            # раньше срока", а не источник истины). Значения в теле — для
            # человека/логов.
            msg.body = (
                f"{self.process_key}: версия параметров v{version} — принято: {summary}. "
                f"reminder_days={updated_params.reminder_days}, escalation_days={updated_params.escalation_days}"
            )
            await self.send(msg)

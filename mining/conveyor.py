"""Конвейер интеллектуального анализа процессов (T-40, ФТ-С-7.1).

По журналу событий за цикл: conformance checking (насколько факт разошёлся с
нормативной BPMN-моделью — fitness/precision/отклонения через alignments,
pm4py) плюс доменный временной срез по контрольным точкам (mining/control_points.py):
факт срабатывания напоминания/эскалации для конкретной задачи в конкретном
экземпляре — прямой сигнал просрочки ЭТОГО шага, не требующий отдельного
вычисления SLA (норматив уже зашит в таймеры BPMN).

Discovery (восстановление фактической модели из журнала, pm4py inductive
miner) в v1 не реализовано — приоритет отдан conformance checking, который
и даёт основной сигнал для контура адаптации (расхождение с нормативом).
Discovery полезен как визуализация "как это было на самом деле", но не
обязателен для алгоритма корректировок (T-41).

Это НЕ алгоритм коррекции (T-41 — отдельная, более крупная задача, главный
научный результат, mining/corrections.py). Здесь только измерение: где и
насколько факт разошёлся с регламентом. Результат (ConveyorReport) — сырьё,
которое T-41 превращает в конкретные корректировки параметров процесса.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pm4py

from eventlog.xes_export import load_event_log_df

from .control_points import ControlPoint


@dataclass
class ControlPointStats:
    """Статистика по одной контрольной точке (одной задаче) за цикл.

    on_time — исполнена до срабатывания напоминания; reminded — успела до
    эскалации, но после напоминания; escalated — не успела и до эскалации
    (самый серьёзный сигнал систематической просрочки этого шага).
    """

    task: str
    n_cases: int
    on_time: int
    reminded: int
    escalated: int

    @property
    def late_fraction(self) -> float:
        return (self.reminded + self.escalated) / self.n_cases if self.n_cases else 0.0

    @property
    def escalated_fraction(self) -> float:
        return self.escalated / self.n_cases if self.n_cases else 0.0

    def __str__(self) -> str:
        return (
            f"{self.task}: вовремя {self.on_time}, с напоминанием {self.reminded}, "
            f"с эскалацией {self.escalated} (из {self.n_cases})"
        )

    def to_dict(self) -> dict:
        return {
            "task": self.task, "n_cases": self.n_cases, "on_time": self.on_time,
            "reminded": self.reminded, "escalated": self.escalated,
            "late_fraction": round(self.late_fraction, 4),
            "escalated_fraction": round(self.escalated_fraction, 4),
        }


@dataclass
class ConveyorReport:
    """Известное ограничение (не устраняется в v1): конвертация BPMN → сеть
    Петри в pm4py не вполне точно передаёт семантику граничных событий. Для
    demo-модели с P7D/P14D-таймерами на review_request экземпляры без
    эскалации получают fitness=1.000, экземпляры с эскалацией — ровно 0.667
    (переходы remind/escalate в производной сети Петри оказываются не
    привязаны причинно к review_request). Это ограничение самого механизма
    BPMN→Petri конвертации pm4py, не ошибка модели или журнала — временной
    сигнал просрочки (control_points ниже) точен и не завязан на структурный
    conformance, он читается напрямую из факта появления remind/escalate в
    журнале конкретного экземпляра.
    """

    process_key: str
    n_cases: int
    fitness: float | None          # доля нормативного поведения, покрытая журналом (alignments)
    precision: float | None        # доля поведения журнала, допустимого моделью
    skipped_activities: Counter = field(default_factory=Counter)   # активность -> сколько раз пропущена (model move)
    unexpected_activities: Counter = field(default_factory=Counter)  # активность -> сколько раз лишняя (log move)
    control_points: dict[str, ControlPointStats] = field(default_factory=dict)  # task -> статистика по шагу

    def __str__(self) -> str:
        fit = f"{self.fitness:.2f}" if self.fitness is not None else "—"
        prec = f"{self.precision:.2f}" if self.precision is not None else "—"
        skipped = ", ".join(f"{a}×{n}" for a, n in self.skipped_activities.most_common()) or "нет"
        cps = "\n".join(f"  {cp}" for cp in self.control_points.values()) or "  нет контрольных точек"
        return (
            f"{self.process_key}: {self.n_cases} экземпляров, fitness={fit}, precision={prec}\n"
            f"  пропуски шагов: {skipped}\n"
            f"{cps}"
        )

    def to_dict(self) -> dict:
        """Для сохранения в analysis_reports.report (JSONB) — ФТ-А-А-5, воспроизводимость."""
        return {
            "process_key": self.process_key,
            "n_cases": self.n_cases,
            "fitness": self.fitness,
            "precision": self.precision,
            "skipped_activities": dict(self.skipped_activities),
            "unexpected_activities": dict(self.unexpected_activities),
            "control_points": {task: cp.to_dict() for task, cp in self.control_points.items()},
        }


def _load_normative_petri_net(bpmn_file: Path):
    bpmn_graph = pm4py.read_bpmn(str(bpmn_file))
    net, im, fm = pm4py.convert_to_petri_net(bpmn_graph)
    # pm4py помечает переходы для conformance/alignments атрибутом `label`,
    # который берётся из человекочитаемого BPMN name ("Эскалация"), а не из
    # id элемента ("escalate"). Наш event_log хранит id (SpiffWorkflow
    # task_spec.name = XML id, не name — см. orchestrator/specs.py) — без
    # этой нормализации label и concept:name никогда не совпадают, и
    # fitness/precision тривиально обнуляются, хотя журнал полностью
    # соответствует модели.
    for t in net.transitions:
        if t.label is not None:
            t.label = t.name
    return net, im, fm


def _control_point_stats(log_df, control_points: list[ControlPoint]) -> dict[str, ControlPointStats]:
    by_case = log_df.groupby("case:concept:name")["concept:name"].apply(set)
    n_cases = len(by_case)
    stats: dict[str, ControlPointStats] = {}
    for cp in control_points:
        escalated = int(by_case.apply(lambda acts: cp.escalation_activity in acts).sum()) \
            if cp.escalation_activity else 0
        reminded_or_worse = int(by_case.apply(lambda acts: cp.reminder_activity in acts).sum()) \
            if cp.reminder_activity else escalated
        reminded_only = reminded_or_worse - escalated
        on_time = n_cases - reminded_or_worse
        stats[cp.task] = ControlPointStats(
            task=cp.task, n_cases=n_cases, on_time=on_time, reminded=reminded_only, escalated=escalated,
        )
    return stats


def analyze_cycle(
    database_url: str,
    process_key: str,
    bpmn_file: Path,
    control_points: list[ControlPoint],
    case_ids: list[str] | None = None,
) -> ConveyorReport:
    log_df = load_event_log_df(database_url, process_key=process_key, case_ids=case_ids)
    n_cases = log_df["case:concept:name"].nunique()

    net, im, fm = _load_normative_petri_net(bpmn_file)

    # Структурному conformance checking скармливаем только те активности,
    # которые реально существуют как переходы модели. Наш event_log богаче
    # BPMN-модели по конструкции (ФТ-С-5.1): туда пишутся и административные
    # события — старт/финал процесса, входы/выходы StartEvent/EndEvent
    # ("process_instance", "start", "end_main"...), которых в модели нет и
    # быть не может. Без фильтра они системно считаются "лишними" (log move)
    # в КАЖДОЙ трассе и обнуляют precision независимо от реального качества
    # соответствия. Домен-специфичные метрики просрочки считаются по полному
    # журналу отдельно, это ограничение их не касается.
    known_labels = {t.label for t in net.transitions if t.label is not None}
    conformance_df = log_df[log_df["concept:name"].isin(known_labels)]

    fitness = None
    precision = None
    skipped: Counter = Counter()
    unexpected: Counter = Counter()
    try:
        fitness_result = pm4py.fitness_alignments(conformance_df, net, im, fm)
        fitness = fitness_result.get("averageFitness") or fitness_result.get("average_trace_fitness")

        precision = pm4py.precision_alignments(conformance_df, net, im, fm)

        diagnostics = pm4py.conformance_diagnostics_alignments(conformance_df, net, im, fm)
        for trace_diag in diagnostics:
            for move in trace_diag.get("alignment", []):
                log_move, model_move = move[0]
                if model_move is not None and log_move is None:
                    skipped[model_move] += 1
                elif log_move is not None and model_move is None and log_move != ">>":
                    unexpected[log_move] += 1
    except Exception:
        # discovery/conformance на пустом или вырожденном журнале не должны валить весь конвейер —
        # отчёт просто останется без метрик соответствия, это видно потребителю (fitness=None).
        pass

    return ConveyorReport(
        process_key=process_key,
        n_cases=n_cases,
        fitness=fitness,
        precision=precision,
        skipped_activities=skipped,
        unexpected_activities=unexpected,
        control_points=_control_point_stats(log_df, control_points),
    )


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1]))
    from api.config import settings  # noqa: E402
    from .control_points import DEMO_CONTROL_POINTS  # noqa: E402

    parser = argparse.ArgumentParser(description="Конвейер анализа процессов (T-40)")
    parser.add_argument("--process-key", required=True)
    parser.add_argument("--bpmn", type=Path, required=True)
    args = parser.parse_args()

    report = analyze_cycle(settings.database_url, args.process_key, args.bpmn, DEMO_CONTROL_POINTS)
    print(report)

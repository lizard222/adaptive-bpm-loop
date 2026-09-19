"""Разовый запуск цикла анализа для реального процесса (не смоук-тест —
здесь нет проверок/PASS-FAIL, только человеко-читаемый отчёт для ручной
проверки fitness/precision и контура корректировок через UI).

В отличие от agents/vkr_defense_smoke_test.py, здесь работает НАСТОЯЩИЙ
InterfaceAgent (не стаб-"завкафедрой") — если алгоритм предложит
корректировку, она реально попадёт в pending_decisions и будет видна на
экране «Корректировки» в UI, а не потеряется внутри одноразового скрипта.

Считает по ВСЕМ событиям с данным process_key в event_log (case_ids=None в
mining.conveyor.analyze_cycle) — то есть по всем экземплярам, которые вы
создали вручную через "Запустить процесс" в UI.

Запуск: python -m agents.run_analysis_cycle [--process-key vkr_defense]
"""
from __future__ import annotations

import argparse
import sys

from .xmpp_dev import enable_unencrypted_plain_auth

enable_unencrypted_plain_auth()

import spade  # noqa: E402

from api.config import settings  # noqa: E402
from mining.control_points import VKR_DEFENSE_CONTROL_POINTS  # noqa: E402
from orchestrator.process_registry import PROCESS_REGISTRY  # noqa: E402

from .analyst_adapter_agent import AnalystAdapterAgent  # noqa: E402
from .interface_agent import InterfaceAgent  # noqa: E402

PASSWORD = "analysis-cycle-password"

# Контрольные точки известны заранее по каждой реальной модели (как и в
# api/dashboard.py::_CONTROLLER_ACTIVITIES) — сейчас в реестре только
# vkr_defense, появится второй реальный процесс — добавить сюда же.
_CONTROL_POINTS_BY_PROCESS = {
    "vkr_defense": VKR_DEFENSE_CONTROL_POINTS,
}


async def main(process_key: str) -> int:
    reg = PROCESS_REGISTRY.get(process_key)
    if reg is None:
        print(f"Неизвестный process_key: {process_key!r} — нет в orchestrator/process_registry.py")
        return 1
    control_points = _CONTROL_POINTS_BY_PROCESS.get(process_key)
    if control_points is None:
        print(f"Нет зарегистрированных контрольных точек для {process_key!r} в этом скрипте")
        return 1

    interface_jid = "analysis-interface@localhost"
    adapter_jid = "analysis-adapter@localhost"

    interface = InterfaceAgent(interface_jid, PASSWORD, settings.database_url, tick_seconds=1.0)
    await interface.start(auto_register=True)
    adapter = AnalystAdapterAgent(
        adapter_jid, PASSWORD, settings.database_url,
        recipient_jid=interface_jid, notify_jids=[], decision_timeout=8.0,
    )
    await adapter.start(auto_register=True)

    print(f"Анализирую process_key={process_key!r} по журналу событий (все экземпляры)...\n")
    result = await adapter.process_cycle(process_key, reg.bpmn_file, control_points, mode="propose")

    print(f"n_cases (в журнале, включая активные): {result.report.n_cases}")
    print(f"fitness:                               {result.report.fitness}")
    print(f"precision:                             {result.report.precision}")
    print("\nПо контрольным точкам:")
    for task, stats in result.report.control_points.items():
        print(f"  {stats}")

    print(f"\nПредложено корректировок: {len(result.proposed)}")
    for c in result.proposed:
        print(f"  - {c.kind} / {c.target}: {c.justification}")

    if result.proposed:
        print(
            f"\nПринято сразу: {len(result.accepted)}, отклонено сразу: {len(result.rejected)}.\n"
            "Если оба нуля — предложения ушли в pending_decisions и ждут решения "
            "человека: откройте «Корректировки» в UI под dept_head/admin."
        )
    else:
        print(
            "\nКорректировок нет — контур не нашёл систематических отклонений "
            "(ожидаемо: реальные таймеры на днях, экземпляры ещё слишком свежие, "
            "чтобы реально просрочиться)."
        )

    await adapter.stop()
    await interface.stop()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Разовый запуск цикла анализа (fitness/precision/корректировки)")
    parser.add_argument("--process-key", default="vkr_defense")
    args = parser.parse_args()
    sys.exit(spade.run(main(args.process_key)))

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

Запуск: python -m agents.run_analysis_cycle [--process-key vkr_defense] [--since 2026-09-26]
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone

from .xmpp_dev import enable_unencrypted_plain_auth

enable_unencrypted_plain_auth()

import psycopg  # noqa: E402
import spade  # noqa: E402

from api.config import settings  # noqa: E402
from mining.control_points import VKR_DEFENSE_CONTROL_POINTS, VKR_DEFENSE_MONITORED_STEPS  # noqa: E402
from orchestrator.process_registry import PROCESS_REGISTRY  # noqa: E402

from .analyst_adapter_agent import AnalystAdapterAgent  # noqa: E402
from .model_store import control_points_for, current_model_file, current_version, step_norm  # noqa: E402
from .interface_agent import InterfaceAgent  # noqa: E402

PASSWORD = "analysis-cycle-password"

# Контрольные точки известны заранее по каждой реальной модели (как и в
# api/dashboard.py::_CONTROLLER_ACTIVITIES) — сейчас в реестре только
# vkr_defense, появится второй реальный процесс — добавить сюда же.
_CONTROL_POINTS_BY_PROCESS = {
    "vkr_defense": VKR_DEFENSE_CONTROL_POINTS,
    # vkr_defense_fast использует те же имена шагов/активностей, что и
    # vkr_defense (только таймеры в минутах, см. process_registry.py) —
    # контрольные точки переиспользуются без изменений.
    "vkr_defense_fast": VKR_DEFENSE_CONTROL_POINTS,
}
_MONITORED_BY_PROCESS = {
    "vkr_defense": VKR_DEFENSE_MONITORED_STEPS,
    "vkr_defense_fast": VKR_DEFENSE_MONITORED_STEPS,
}


def _resolve_case_ids(process_key: str, exclude: list[str], since: datetime | None = None) -> list[str] | None:
    """event_log неизменяем (ФТ-С-5.2, триггер запрещает UPDATE/DELETE) —
    известные испорченные case_id (например, задетые найденным багом
    tick_all без фильтра по process_key, см. orchestrator/engine.py) нельзя
    убрать из журнала. Единственный честный способ пересчитать fitness/
    precision без них — явно передать mining.conveyor.analyze_cycle список
    ИСКЛЮЧАЯ эти case_id, а не полагаться на case_ids=None (все).

    since — то же для смены версии модели (E13: vkr_defense вырос с 4 до 7
    шагов): экземпляры, начатые до этого момента, шли по старой модели и
    сравнивать их с новой бессмысленно — fitness упадёт не из-за отклонений,
    а из-за другой схемы. Берутся case_id, первое событие которых >= since."""
    if not exclude and since is None:
        return None  # без фильтров — анализируем все case_id как обычно
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            "SELECT case_id, min(ts) FROM event_log WHERE process_key = %s GROUP BY case_id", (process_key,)
        ).fetchall()
    all_ids = [c for c, _ in rows]
    excluded_set = set(exclude)
    kept = [c for c, first_ts in rows if c not in excluded_set and (since is None or first_ts >= since)]
    missing = excluded_set - set(all_ids)
    if missing:
        print(f"Предупреждение: не найдены в журнале (опечатка в --exclude-case-id?): {sorted(missing)}")
    if exclude:
        print(f"Исключено из анализа явно: {len(excluded_set & set(all_ids))} case_id из {len(all_ids)}")
    if since is not None:
        older = sum(1 for _, first_ts in rows if first_ts < since)
        print(f"Начаты до {since.isoformat()} (не анализируются): {older} case_id из {len(all_ids)}")
    print(f"В анализ идут: {len(kept)} case_id")
    return kept


async def main(process_key: str, exclude: list[str], wait_seconds: float,
               since: datetime | None = None) -> int:
    reg = PROCESS_REGISTRY.get(process_key)
    if reg is None:
        print(f"Неизвестный process_key: {process_key!r} — нет в orchestrator/process_registry.py")
        return 1
    control_points = _CONTROL_POINTS_BY_PROCESS.get(process_key)
    if control_points is None:
        print(f"Нет зарегистрированных контрольных точек для {process_key!r} в этом скрипте")
        return 1
    case_ids = _resolve_case_ids(process_key, exclude, since)

    # JID уникален на каждый запуск (как в смоук-тестах, RUN_ID) — иначе
    # decided-но-не-отправленное решение из ПРЕДЫДУЩЕГО запуска (человек
    # принял решение уже после того, как тот скрипт завершился и отключился)
    # при следующем запуске находит агента с ТЕМ ЖЕ JID и шлёт ему сообщение,
    # которое некому обработать ("No behaviour matched for message") —
    # реально наблюдалось при разработке этого скрипта.
    run_id = uuid.uuid4().hex[:8]
    interface_jid = f"analysis-interface-{run_id}@localhost"
    adapter_jid = f"analysis-adapter-{run_id}@localhost"

    interface = InterfaceAgent(interface_jid, PASSWORD, settings.database_url, tick_seconds=1.0)
    await interface.start(auto_register=True)
    # default_params — базовые сроки ЭТОГО процесса из реестра. Без них агент
    # брал свой умолчательный 7/14 и, применяя корректировку к процессу без
    # сохранённых параметров, записывал их: у vkr_defense_fast (1/2 минуты)
    # сроки молча становились 7/14 минут (найдено на демонстрации E15, 25.10.2026).
    adapter = AnalystAdapterAgent(
        adapter_jid, PASSWORD, settings.database_url,
        recipient_jid=interface_jid, notify_jids=[], decision_timeout=wait_seconds,
        default_params=reg.default_params,
    )
    await adapter.start(auto_register=True)

    print(f"Анализирую process_key={process_key!r} по журналу событий...\n")
    print(
        f"Если появятся предложения — у вас будет {wait_seconds:.0f} сек., чтобы принять/отклонить "
        "их в UI («Корректировки», роль dept_head/admin). Не успеете — предложение всё равно "
        "останется в pending_decisions ждать решения, но применится оно ТОЛЬКО если вы решите "
        "внутри этого окна: агент этого скрипта отключится по истечении времени и уже не увидит "
        "ваш более поздний ответ — постоянного рантайма агентов в прототипе нет (см. README)."
    )
    # E15: анализ по текущей версии модели — с контрольными точками, добавленными
    # прошлыми корректировками; шаги без контроля — с нормой длительности.
    model_version, _ = current_version(settings.database_url, process_key)
    print(f"Версия модели: v{model_version}")
    result = await adapter.process_cycle(
        process_key, current_model_file(settings.database_url, process_key),
        control_points_for(settings.database_url, process_key, control_points),
        case_ids=case_ids, mode="propose",
        monitored_steps=_MONITORED_BY_PROCESS.get(process_key), norm=step_norm(settings.database_url, process_key),
    )

    print(f"n_cases (в журнале, включая активные): {result.report.n_cases}")
    print(f"fitness:                               {result.report.fitness}")
    print(f"precision:                             {result.report.precision}")
    print("\nПо контрольным точкам:")
    for task, stats in result.report.control_points.items():
        print(f"  {stats}")
    if result.report.monitored_steps:
        print("Шаги без контрольной точки:")
        for stats in result.report.monitored_steps.values():
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


def _parse_since(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Разовый запуск цикла анализа (fitness/precision/корректировки)")
    parser.add_argument("--process-key", default="vkr_defense")
    parser.add_argument(
        "--exclude-case-id", action="append", default=[],
        help="Исключить case_id из анализа (можно повторять несколько раз) — "
             "для известных испорченных экземпляров, которые нельзя удалить из "
             "неизменяемого event_log",
    )
    parser.add_argument(
        "--wait-seconds", type=float, default=300.0,
        help="Сколько ждать решения человека в UI, если контур предложит "
             "корректировку (по умолчанию 5 минут — реалистичное окно для "
             "ручного тестирования, не 8 секунд, как раньше)",
    )
    parser.add_argument(
        "--since", type=_parse_since, default=None,
        help="Анализировать только экземпляры, начатые не раньше этого момента "
             "(ISO-дата или дата-время, без зоны = UTC) — чтобы отделить экземпляры "
             "прежней версии модели",
    )
    args = parser.parse_args()
    sys.exit(spade.run(main(args.process_key, args.exclude_case_id, args.wait_seconds, args.since)))

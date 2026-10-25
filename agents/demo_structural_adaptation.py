"""Демонстрация структурной адаптации на тестовой модели — для ручной проверки в UI (E15).

Без скрипта ручная проверка — это 6–8 защит, каждую провести по шагам под
четырьмя ролями и специально задержать отзыв руководителя: десятки действий.
Скрипт берёт рутину на себя, а решение остаётся за человеком в UI:

  1. Запускает N защит тестовой модели vkr_defense_fast (сроки в минутах) и
     проводит их по шагам от имени ролей дорожек. На контролируемых шагах —
     сразу (без напоминаний), а «Отзыв руководителя и рецензия» у части защит
     выполняет только через 90 секунд — дольше нормы (срок напоминания, 1 мин).
  2. Запускает анализ (agents/run_analysis_cycle.py) только по этим защитам.
     Анализ предлагает добавить контрольную точку на отзыв; предложение ждёт
     решения на «Корректировках» под dept_head (до --wait-seconds).
  3. Если корректировку приняли — модель стала v1: скрипт запускает новую
     защиту для студента student и доводит её до отзыва. Через минуту по
     отзыву срабатывает напоминание — его видно в «Задачах» (у отзыва
     появился срок) и в «Моей защите» студента.

Нужны: docker-контейнеры (PostgreSQL, Prosody) и uvicorn (для UI).
Запуск: python -m agents.demo_structural_adaptation [--instances 8] [--slow 5]
        python -m agents.demo_structural_adaptation --reset  — вернуть модель
        vkr_defense_fast к базовой версии (удалить версии модели), чтобы
        повторить демонстрацию.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone

from .xmpp_dev import enable_unencrypted_plain_auth

enable_unencrypted_plain_auth()

import psycopg  # noqa: E402
import spade  # noqa: E402

from api.config import settings  # noqa: E402
from api.participants import STUDENT, bind  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402
from orchestrator.process_registry import PROCESS_REGISTRY  # noqa: E402

from . import run_analysis_cycle  # noqa: E402
from .model_store import GENERATED_DIR, current_model_file, current_version  # noqa: E402
from .params_store import get_current_params  # noqa: E402

PROCESS_KEY = "vkr_defense_fast"
REVIEW = "supervisor_review"
SLOW_SECONDS = 90
# Кто выполняет шаг — по дорожкам модели (resource в журнале)
ROLE_BY_STEP = {
    "approve_topics": "secretary", "report_2": "supervisor", "publish_for_normcontrol": "student",
    "normcontrol": "normcontrol", "publish_final": "student", REVIEW: "supervisor",
    "admission_order": "secretary", "defense": "secretary",
}
BEFORE_REVIEW = ["approve_topics", "report_2", "publish_for_normcontrol", "normcontrol", "publish_final"]
AFTER_REVIEW = ["admission_order", "defense"]


def _launch(orch: Orchestrator, student: str | None = None) -> str:
    """Как ручной запуск в UI (api/processes.py): последняя версия модели, текущие параметры."""
    reg = PROCESS_REGISTRY[PROCESS_KEY]
    case_id = f"{PROCESS_KEY}-demo-{uuid.uuid4().hex[:6]}"
    params = get_current_params(settings.database_url, PROCESS_KEY, reg.default_params)
    orch.start_instance(case_id, PROCESS_KEY, current_model_file(settings.database_url, PROCESS_KEY), reg.process_id,
                        initial_data=params.as_initial_data(), attributes={"demo": "structural_adaptation"})
    if student:
        with psycopg.connect(settings.database_url) as conn:
            bind(conn, case_id, STUDENT, student)
            conn.commit()
    return case_id


def _complete(orch: Orchestrator, case_ids: list[str], step: str) -> None:
    for c in case_ids:
        orch.complete_task(c, step, resource=ROLE_BY_STEP[step])


def _reset() -> int:
    with psycopg.connect(settings.database_url) as conn:
        n = conn.execute("DELETE FROM process_model_versions WHERE process_key = %s", (PROCESS_KEY,)).rowcount
        conn.commit()
    for f in GENERATED_DIR.glob(f"{PROCESS_KEY}.v*.bpmn"):
        f.unlink()
    print(f"Удалено версий модели {PROCESS_KEY}: {n}. Новые защиты пойдут по базовой модели; "
          f"уже запущенные доходят по своей.")
    return 0


async def _demo(n_instances: int, n_slow: int, wait_seconds: float) -> int:
    orch = Orchestrator(settings.database_url)
    version, added = current_version(settings.database_url, PROCESS_KEY)
    if REVIEW in added:
        print(f"У {PROCESS_KEY} уже модель v{version} с контрольной точкой на отзыве — демонстрировать нечего.\n"
              f"Вернуть базовую модель: python -m agents.demo_structural_adaptation --reset")
        return 1

    started = datetime.now(timezone.utc)
    print(f"Шаг 1/3. Запускаю {n_instances} защит {PROCESS_KEY} (модель v{version}) и провожу их по шагам.")
    cases = [_launch(orch) for _ in range(n_instances)]
    for step in BEFORE_REVIEW:
        _complete(orch, cases, step)
        print(f"  все {n_instances}: «{step}» выполнен ({ROLE_BY_STEP[step]})")

    slow, fast = cases[:n_slow], cases[n_slow:]
    _complete(orch, fast, REVIEW)
    print(f"  {len(fast)} защит: отзыв выполнен сразу")
    print(f"  {len(slow)} защит: отзыв затягивается — жду {SLOW_SECONDS} с (норма — срок напоминания, 1 мин)")
    for left in range(SLOW_SECONDS, 0, -15):
        print(f"    осталось {left} с")
        await asyncio.sleep(min(15, left))
    _complete(orch, slow, REVIEW)
    for step in AFTER_REVIEW:
        _complete(orch, cases, step)
    print(f"  все {n_instances} защит завершены.\n")

    print("Шаг 2/3. Анализ журнала этих защит. Откройте http://localhost:5173 под dept_head → «Корректировки»: "
          "там появится «Добавление контрольной точки» на supervisor_review — примите его.\n")
    await run_analysis_cycle.main(PROCESS_KEY, [], wait_seconds, started)

    version, added = current_version(settings.database_url, PROCESS_KEY)
    if REVIEW not in added:
        print("\nКорректировку не приняли (или не успели) — модель осталась прежней. "
              "Можно запустить скрипт ещё раз.")
        return 1

    print(f"\nШаг 3/3. Модель {PROCESS_KEY} теперь v{version}: контрольная точка на отзыве.")
    case_id = _launch(orch, student="student")
    for step in BEFORE_REVIEW:
        _complete(orch, [case_id], step)
    print(f"  Новая защита {case_id} (студент student) запущена по v{version} и ждёт отзыва руководителя.\n"
          "  Что посмотреть в UI:\n"
          "   • «Процессы» → vkr_defense_fast: метка «модель v1» и строка о добавленной точке;\n"
          "   • «Задачи» под supervisor: у отзыва этой защиты теперь есть срок (раньше — «—»);\n"
          "   • через ~1 минуту — напоминание: «Моя защита» под student, лента: "
          "«Напоминание: подходит срок этапа «Отзыв руководителя и рецензия»»;\n"
          "   • через ~2 минуты — эскалация. Она, как и на остальных относительных точках рабочей\n"
          "     модели, прерывающая: защита завершится. Чтобы защита пошла дальше, выполните отзыв\n"
          "     под supervisor в «Задачах» раньше.\n"
          "  Повторить демонстрацию с начала: python -m agents.demo_structural_adaptation --reset")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Демонстрация структурной адаптации на vkr_defense_fast")
    parser.add_argument("--instances", type=int, default=8)
    parser.add_argument("--slow", type=int, default=5, help="у скольких защит отзыв затянется дольше нормы")
    parser.add_argument("--wait-seconds", type=float, default=300.0,
                        help="сколько ждать решения на «Корректировках»")
    parser.add_argument("--reset", action="store_true", help="вернуть модель vkr_defense_fast к базовой")
    args = parser.parse_args()
    if args.reset:
        sys.exit(_reset())
    sys.exit(spade.run(_demo(args.instances, args.slow, args.wait_seconds)))

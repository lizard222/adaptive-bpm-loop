"""Фоновый цикл продвижения таймеров BPMN (найдено и закрыто 19.09.2026).

ДО этого файла живая система (всё, что идёт через api/*, то есть REST и UI)
НИКОГДА сама не проверяла граничные таймеры экземпляров — Orchestrator.tick()/
tick_all() вызывались только из смоук-тестов, генератора simgen (под
управляемым временем freezegun) и из agents/scheduler_agent.py::LaunchTick,
который сам по себе никогда не запускается как персистентный процесс (см.
README, «постоянного рантайма агентов в прототипе нет»). Итог: даже
экземпляр с таймером в одну минуту не эскалировал бы САМ ПО СЕБЕ никогда,
сколько бы реального времени ни прошло — таймер BPMN не срабатывает "по
будильнику", кто-то обязан явно спросить "не истекло ли что-нибудь".

Решение — простой фоновый asyncio-цикл внутри самого uvicorn: единственное
место, которое реально приводит живой REST/UI-контур в движение сам по себе,
без ручного запуска скриптов. Интервал (15 сек) выбран для отзывчивости на
короткие тестовые таймеры (минуты) — для боевых многодневных таймеров это
избыточно часто, но на масштабе прототипа (единицы активных экземпляров)
не создаёт заметной нагрузки; не тюнинговано для продакшена.

ВАЖНО (найдено сразу после первой версии этого файла): цикл тикает ТОЛЬКО
process_key из orchestrator.process_registry.PROCESS_REGISTRY (сейчас —
vkr_defense/vkr_defense_fast), а не буквально всё активное в базе.
Неограниченный tick_all() здесь гонялся бы с simgen.run_cycle/смоук-тестами
(они держат СВОИ экземпляры активными под управляемым временем freezegun,
в отдельном процессе, но в той же БД) — поймано на практике: тест
воспроизводимости по seed (simgen/smoke_test.py) стал ФЛАКОВЫМ (3/4 вместо
4/4) именно из-за того, что этот фоновый цикл в реальном времени вклинивался
между шагами симуляции и тикал её же экземпляры раньше времени. process_key
из PROCESS_REGISTRY и ad-hoc ключи смоук-тестов/эксперимента
(demo_process_days_*, experiment_*, workload_planning_days_* и т.п.) не
пересекаются НИКОГДА по построению (см. docstring process_registry.py) —
поэтому фильтр по реестру полностью исключает эту гонку, а не просто снижает
её вероятность.
"""
from __future__ import annotations

import asyncio
import logging

from orchestrator import Orchestrator
from orchestrator.process_registry import PROCESS_REGISTRY

logger = logging.getLogger("api.background_tick")

TICK_INTERVAL_SECONDS = 15.0


async def background_tick_loop(orchestrator: Orchestrator) -> None:
    while True:
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
        for process_key in PROCESS_REGISTRY:
            try:
                # tick_all() — синхронный, блокирующий psycopg-вызов; уводим
                # в поток, чтобы не подвешивать event loop FastAPI на время
                # БД-round-trip.
                ticked = await asyncio.to_thread(orchestrator.tick_all, process_key)
                if ticked:
                    logger.info("Фоновый tick (%s): продвинуто экземпляров: %d", process_key, ticked)
            except Exception:  # noqa: BLE001 — сбой по одному процессу не должен останавливать весь цикл
                logger.exception("Ошибка фонового tick_all() для process_key=%r", process_key)

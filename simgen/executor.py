"""Профиль синтетического исполнителя (T-35, ФТ-С-9.1): решает, через сколько
дней после того, как задача стала READY, "человек" её выполнит — или не
выполнит вовсе (систематическая просрочка/пропуск, которую и должен находить
контур адаптации, T-41).

Задержка — логнормальное распределение (типично для времени реакции людей:
длинный правый хвост, медиана положительна, отрицательных значений не бывает).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class ExecutorProfile:
    delay_median_days: float = 3.0
    delay_sigma: float = 0.7
    no_show_probability: float = 0.15

    def sample_delay_days(self, rng: random.Random) -> float | None:
        """None означает "не выполнит вовсе" — систематический пропуск шага."""
        if rng.random() < self.no_show_probability:
            return None
        mu = math.log(max(self.delay_median_days, 0.01))
        return rng.lognormvariate(mu, self.delay_sigma)

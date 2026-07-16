# -*- coding: utf-8 -*-
"""Графики и сводные таблицы по результатам эксперимента (T-54).

Строит из CSV (experiment/run_experiment.write_csv):
  1. figures/escalated_fraction.png — сходимость adaptive к baseline по циклам
     (главный график: подтверждает или опровергает гипотезу диссертации)
  2. figures/parameter_evolution.png — как контур адаптации меняет параметры
     процесса от цикла к циклу (диагностика механизма)
  3. RESULTS.md — сводные таблицы (среднее±std по циклам, парное сравнение
     последнего цикла) в markdown, готовые для вставки в главу 4

Оформление — по методу skill dataviz: категориальная палитра (2 серии,
проверена валидатором на цветовую слепоту, ΔE 24.7–33.6 при пороге 8: blue
#2a78d6 / orange #eb6834), одна ось, тонкие линии, дополнительно разный
стиль линии (пунктир/сплошная) — устойчиво к чёрно-белой печати в тексте
диссертации, где палитра не поможет.

Запуск: python -m experiment.plots experiment/results_reduced.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — без всплывающих окон
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd

# Палитра (dataviz skill, validate_palette.js — PASS, см. experiment/DESIGN.md).
COLOR_BASELINE = "#2a78d6"   # blue — контроль
COLOR_ADAPTIVE = "#eb6834"   # orange — вмешательство
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"

REGIME_STYLE = {
    "baseline": {"color": COLOR_BASELINE, "linestyle": "--", "label": "baseline"},
    "adaptive": {"color": COLOR_ADAPTIVE, "linestyle": "-", "label": "adaptive"},
}


def _style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(INK_MUTED)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9)
    ax.grid(True, color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))  # циклы дискретны, не дробные


def plot_escalated_fraction(df: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.5), facecolor=SURFACE)
    _style_axes(ax)

    for regime, style in REGIME_STYLE.items():
        g = df[df["regime"] == regime].groupby("cycle")["escalated_fraction"]
        mean = g.mean()
        std = g.std().fillna(0.0)
        ax.plot(mean.index, mean.values, color=style["color"], linestyle=style["linestyle"],
                 linewidth=2, label=style["label"], zorder=3)
        ax.fill_between(mean.index, (mean - std).clip(lower=0), (mean + std),
                         color=style["color"], alpha=0.12, linewidth=0, zorder=2)

    ax.set_xlabel("цикл (семестр)", color=INK_SECONDARY, fontsize=10)
    ax.set_ylabel("доля эскалаций", color=INK_SECONDARY, fontsize=10)
    ax.set_title("Систематическая просрочка: baseline vs adaptive",
                 color=INK_PRIMARY, fontsize=12, loc="left", pad=12)
    ax.set_ylim(bottom=0)
    legend = ax.legend(frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_parameter_evolution(df: pd.DataFrame, out: Path) -> None:
    adaptive = df[df["regime"] == "adaptive"]
    fig, ax = plt.subplots(figsize=(7, 4.5), facecolor=SURFACE)
    _style_axes(ax)

    esc = adaptive.groupby("cycle")["escalation_days"].mean()
    rem = adaptive.groupby("cycle")["reminder_days"].mean()
    ax.plot(esc.index, esc.values, color=COLOR_ADAPTIVE, linestyle="-", linewidth=2,
             label="escalation_days", zorder=3)
    ax.plot(rem.index, rem.values, color=COLOR_BASELINE, linestyle="-.", linewidth=2,
             label="reminder_days", zorder=3)

    ax.set_xlabel("цикл (семестр)", color=INK_SECONDARY, fontsize=10)
    ax.set_ylabel("дней", color=INK_SECONDARY, fontsize=10)
    ax.set_title("Контур адаптации: рост параметров процесса (только adaptive)",
                 color=INK_PRIMARY, fontsize=12, loc="left", pad=12)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def build_tables(df: pd.DataFrame, n_cycles: int) -> str:
    agg = (
        df.groupby(["regime", "cycle"])["escalated_fraction"]
        .agg(["mean", "std", "count"])
        .round(3)
        .reset_index()
    )

    lines = ["| regime | cycle | mean escalated_fraction | std | n_seeds |", "|---|---|---|---|---|"]
    for _, row in agg.iterrows():
        lines.append(f"| {row['regime']} | {int(row['cycle'])} | {row['mean']:.3f} | {row['std']:.3f} | {int(row['count'])} |")
    per_cycle_table = "\n".join(lines)

    last = n_cycles - 1
    baseline_last = df[(df.regime == "baseline") & (df.cycle == last)].set_index("seed")["escalated_fraction"]
    adaptive_last = df[(df.regime == "adaptive") & (df.cycle == last)].set_index("seed")["escalated_fraction"]
    seeds = sorted(set(baseline_last.index) & set(adaptive_last.index))
    diffs = [adaptive_last[s] - baseline_last[s] for s in seeds]
    improved = sum(1 for d in diffs if d < 0)

    summary = (
        f"**Последний цикл (cycle={last})**: baseline={baseline_last.loc[seeds].mean():.3f}, "
        f"adaptive={adaptive_last.loc[seeds].mean():.3f}, "
        f"среднее изменение по seed {sum(diffs) / len(diffs):+.3f}, "
        f"улучшение в {improved}/{len(seeds)} seed(ах)."
    )

    return per_cycle_table, summary


def main(csv_path: Path) -> int:
    df = pd.read_csv(csv_path)
    n_cycles = df["cycle"].max() + 1
    figures_dir = Path(__file__).parent / "figures"
    figures_dir.mkdir(exist_ok=True)

    plot_escalated_fraction(df, figures_dir / "escalated_fraction.png")
    plot_parameter_evolution(df, figures_dir / "parameter_evolution.png")
    per_cycle_table, summary = build_tables(df, n_cycles)

    report = f"""# Результаты эксперимента (T-54)

> Источник данных: `{csv_path.name}` ({df['seed'].nunique()} seed × {n_cycles} циклов × 2 режима).
> Дизайн и методология — `experiment/DESIGN.md`.

## Главный график: сходимость adaptive к меньшей доле эскалаций

![escalated_fraction](figures/escalated_fraction.png)

{summary}

## Как меняются параметры процесса (только adaptive)

![parameter_evolution](figures/parameter_evolution.png)

Baseline не показан — параметры там зафиксированы на всех циклах по определению дизайна.

## Таблица по циклам

{per_cycle_table}
"""
    out_md = Path(__file__).parent / "RESULTS.md"
    out_md.write_text(report, encoding="utf-8")
    print(f"Графики -> {figures_dir}")
    print(f"Отчёт -> {out_md}")
    print()
    print(summary)
    return 0


if __name__ == "__main__":
    csv_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "results.csv"
    sys.exit(main(csv_arg))

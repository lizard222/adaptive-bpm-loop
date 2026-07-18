import { useEffect, useState } from "react";
import * as api from "./api.js";
import StatTile from "./StatTile.jsx";
import Badge from "./Badge.jsx";
import { fmtPct, escalationSeverity } from "./format.js";

export default function Processes() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(() => new Set());

  async function refresh() {
    try {
      setData(await api.getDashboardSummary());
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function toggle(key) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <section className="rounded-lg border border-gridline bg-surface p-5 dark:border-white/10 dark:bg-surface-dark">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-ink dark:text-ink-dark">Процессы</h2>
        <button
          onClick={refresh}
          className="rounded-md border border-gridline px-3 py-1.5 text-xs font-medium text-ink-secondary hover:bg-page dark:border-white/10 dark:text-ink-dark-secondary dark:hover:bg-white/5"
        >
          Обновить
        </button>
      </div>
      {error && <p className="mb-4 text-sm text-status-critical">{error}</p>}
      {loading ? (
        <p className="py-6 text-center text-sm text-ink-muted">Загрузка…</p>
      ) : !data || data.processes.length === 0 ? (
        <p className="py-6 text-center text-sm text-ink-muted">Нет данных: ни один процесс ещё не запускался.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {data.processes.map((p) => (
            <ProcessRow
              key={p.process_key}
              process={p}
              isOpen={expanded.has(p.process_key)}
              onToggle={() => toggle(p.process_key)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ProcessRow({ process, isOpen, onToggle }) {
  const { process_key, active_instances, params, latest_report } = process;
  return (
    <div className="rounded-md border border-gridline dark:border-white/10">
      <button onClick={onToggle} className="flex w-full items-center justify-between px-4 py-3 text-left">
        <span className="font-mono text-sm text-ink dark:text-ink-dark">{process_key}</span>
        <span className="flex items-center gap-4 text-xs text-ink-muted">
          <span>{active_instances} активных</span>
          <span>{fmtPct(latest_report?.fitness) ?? "—"} fitness</span>
          <span>{isOpen ? "▲" : "▼"}</span>
        </span>
      </button>
      {isOpen && (
        <div className="border-t border-gridline p-4 dark:border-white/10">
          <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatTile label="Активные экземпляры" value={active_instances} />
            <StatTile label="Fitness" value={fmtPct(latest_report?.fitness)} hint={!latest_report && "нет анализа"} />
            <StatTile label="Precision" value={fmtPct(latest_report?.precision)} hint={!latest_report && "нет анализа"} />
            <StatTile
              label="Параметры"
              value={params ? `${params.reminder_days} / ${params.escalation_days} дн.` : null}
              hint={params ? `версия ${params.version}` : "нет данных"}
            />
          </div>
          {latest_report && latest_report.control_points.length > 0 && (
            <ControlPointsTable rows={latest_report.control_points} />
          )}
        </div>
      )}
    </div>
  );
}

function ControlPointsTable({ rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gridline text-left text-xs uppercase tracking-wide text-ink-muted dark:border-white/10">
            <th className="py-2 pr-3">Задача</th>
            <th className="py-2 pr-3">Экземпляров</th>
            <th className="py-2 pr-3">Вовремя</th>
            <th className="py-2 pr-3">Напоминание</th>
            <th className="py-2 pr-3">Эскалация</th>
            <th className="py-2 pr-3">Доля просрочки</th>
            <th className="py-2">Доля эскалации</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((cp) => {
            const severity = escalationSeverity(cp.escalated_fraction);
            return (
              <tr key={cp.task} className="border-b border-gridline last:border-0 dark:border-white/10">
                <td className="py-2 pr-3 text-ink dark:text-ink-dark">{cp.task}</td>
                <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">{cp.n_cases}</td>
                <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">{cp.on_time}</td>
                <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">{cp.reminded}</td>
                <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">{cp.escalated}</td>
                <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">{fmtPct(cp.late_fraction)}</td>
                <td className="py-2">
                  {severity && (
                    <Badge tone={severity.tone}>
                      {fmtPct(cp.escalated_fraction)} · {severity.label}
                    </Badge>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

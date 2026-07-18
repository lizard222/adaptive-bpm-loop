import { useEffect, useState } from "react";
import * as api from "./api.js";
import StatTile from "./StatTile.jsx";
import Badge from "./Badge.jsx";
import StatusDot from "./StatusDot.jsx";
import { KIND_LABELS } from "./constants.js";
import { fmtDate } from "./format.js";
import { relativeTime, agentTone } from "./time.js";

const DECISION_TONE = { accepted: "good", rejected: "critical" };
const DECISION_LABEL = { accepted: "Принято", rejected: "Отклонено" };

export default function Overview({ user, onNavigate }) {
  const [data, setData] = useState(null);
  const [pendingCount, setPendingCount] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const canSeeCorrections = user.role === "dept_head" || user.role === "admin";

  async function refresh() {
    try {
      const summary = await api.getDashboardSummary();
      setData(summary);
      if (canSeeCorrections) {
        const pending = await api.listPendingCorrections();
        setPendingCount(pending.pending.length);
      }
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

  if (loading) return <p className="py-6 text-center text-sm text-ink-muted">Загрузка…</p>;
  if (error) return <p className="text-sm text-status-critical">{error}</p>;
  if (!data) return null;

  const totalActive = data.processes.reduce((sum, p) => sum + p.active_instances, 0);
  const fitnessValues = data.processes.map((p) => p.latest_report?.fitness).filter((v) => v != null);
  const avgFitness = fitnessValues.length
    ? `${Math.round((fitnessValues.reduce((a, b) => a + b, 0) / fitnessValues.length) * 100)}%`
    : null;

  return (
    <>
      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Активных экземпляров" value={totalActive} />
        <StatTile label="Отслеживаемых процессов" value={data.processes.length} />
        <StatTile label="Средний fitness" value={avgFitness} hint={!avgFitness && "нет анализа"} />
        {canSeeCorrections ? (
          <button onClick={() => onNavigate("corrections")} className="text-left">
            <StatTile label="Ожидают решения" value={pendingCount} />
          </button>
        ) : (
          <StatTile label="Процессов с параметрами" value={data.processes.filter((p) => p.params).length} />
        )}
      </section>

      <section className="flex flex-wrap gap-2">
        <button
          onClick={() => onNavigate("tasks")}
          className="rounded-md border border-gridline px-3 py-1.5 text-xs font-medium text-ink-secondary hover:bg-page dark:border-white/10 dark:text-ink-dark-secondary dark:hover:bg-white/5"
        >
          К задачам
        </button>
        <button
          onClick={() => onNavigate("processes")}
          className="rounded-md border border-gridline px-3 py-1.5 text-xs font-medium text-ink-secondary hover:bg-page dark:border-white/10 dark:text-ink-dark-secondary dark:hover:bg-white/5"
        >
          К процессам
        </button>
        <button
          onClick={() => onNavigate("documents")}
          className="rounded-md border border-gridline px-3 py-1.5 text-xs font-medium text-ink-secondary hover:bg-page dark:border-white/10 dark:text-ink-dark-secondary dark:hover:bg-white/5"
        >
          Сформировать документ
        </button>
      </section>

      <section className="rounded-lg border border-gridline bg-surface p-5 dark:border-white/10 dark:bg-surface-dark">
        <h2 className="mb-4 text-base font-semibold text-ink dark:text-ink-dark">Активные агенты</h2>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {data.agents.map((a) => (
            <li key={a.key} className="flex items-center gap-2 text-sm">
              <StatusDot tone={agentTone(a.last_active)} />
              <span className="text-ink dark:text-ink-dark">{a.label}</span>
              <span className="ml-auto text-xs text-ink-muted">{relativeTime(a.last_active)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-gridline bg-surface p-5 dark:border-white/10 dark:bg-surface-dark">
        <h2 className="mb-4 text-base font-semibold text-ink dark:text-ink-dark">Последние решения</h2>
        {data.recent_decisions.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">Решений пока не было.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {data.recent_decisions.map((d) => (
              <li
                key={d.id}
                className="flex flex-wrap items-center gap-2 border-b border-gridline py-2 text-sm last:border-0 dark:border-white/10"
              >
                <Badge tone={DECISION_TONE[d.status] || "neutral"}>
                  {DECISION_LABEL[d.status] || d.status}
                </Badge>
                <span className="font-mono text-xs text-ink-muted">{d.process_key}</span>
                <span className="text-ink dark:text-ink-dark">{KIND_LABELS[d.kind] || d.kind}</span>
                <span className="text-ink-secondary dark:text-ink-dark-secondary">«{d.target}»</span>
                <span className="ml-auto text-xs text-ink-muted">
                  {d.decided_by} · {fmtDate(d.decided_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

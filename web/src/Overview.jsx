import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "./api.js";
import StatTile from "./components/StatTile.jsx";
import Badge from "./components/Badge.jsx";
import StatusDot from "./components/StatusDot.jsx";
import Card from "./components/Card.jsx";
import { buttonClass } from "./components/Button.jsx";
import LoadingState from "./components/LoadingState.jsx";
import ErrorState from "./components/ErrorState.jsx";
import EmptyState from "./components/EmptyState.jsx";
import { useApiData } from "./useApiData.js";
import { CAN_SEE_CORRECTIONS, hasRole } from "./roles.js";
import { KIND_LABELS } from "./constants.js";
import { fmtDate } from "./format.js";
import { relativeTime, agentTone } from "./time.js";

const DECISION_TONE = { accepted: "good", rejected: "critical" };
const DECISION_LABEL = { accepted: "Принято", rejected: "Отклонено" };

export default function Overview({ user }) {
  const canSeeCorrections = hasRole(user, CAN_SEE_CORRECTIONS);
  const { data, error, loading, refresh } = useApiData(api.getDashboardSummary);
  const [pendingCount, setPendingCount] = useState(null);

  useEffect(() => {
    if (!canSeeCorrections) return;
    api
      .listPendingCorrections()
      .then((p) => setPendingCount(p.pending.length))
      .catch(() => {
        /* Overview показывает сводку — точное число необязательно, ошибку не блокируем */
      });
  }, [canSeeCorrections, data]);

  if (loading) return <LoadingState rows={5} />;
  if (error) return <ErrorState message={error} onRetry={refresh} />;
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
          <Link to="/corrections" className="block text-left">
            <StatTile label="Ожидают решения" value={pendingCount} />
          </Link>
        ) : (
          <StatTile label="Процессов с параметрами" value={data.processes.filter((p) => p.params).length} />
        )}
      </section>

      <section className="flex flex-wrap items-center gap-2">
        <Link to="/tasks" className={buttonClass("secondary")}>
          К задачам
        </Link>
        <Link to="/processes" className={buttonClass("secondary")}>
          К процессам
        </Link>
        <Link to="/documents" className={buttonClass("secondary")}>
          Сформировать документ
        </Link>
        <button
          onClick={refresh}
          className={buttonClass("ghost", "sm", "ml-auto border border-gridline dark:border-white/10")}
        >
          Обновить
        </button>
      </section>

      <Card title="Активные агенты">
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {data.agents.map((a) => (
            <li key={a.key} className="flex items-center gap-2 text-sm">
              <StatusDot tone={agentTone(a.last_active)} />
              <span className="text-ink dark:text-ink-dark">{a.label}</span>
              <span className="ml-auto text-xs text-ink-muted">{relativeTime(a.last_active)}</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Последние решения">
        {data.recent_decisions.length === 0 ? (
          <EmptyState message="Решений пока не было." />
        ) : (
          <ul className="flex flex-col gap-2">
            {data.recent_decisions.map((d) => (
              <li
                key={d.id}
                className="flex flex-wrap items-center gap-2 border-b border-gridline py-2 text-sm last:border-0 dark:border-white/10"
              >
                <Badge tone={DECISION_TONE[d.status] || "neutral"}>{DECISION_LABEL[d.status] || d.status}</Badge>
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
      </Card>
    </>
  );
}

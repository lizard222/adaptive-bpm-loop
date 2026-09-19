import { useState } from "react";
import * as api from "./api.js";
import StatTile from "./components/StatTile.jsx";
import Badge from "./components/Badge.jsx";
import Card from "./components/Card.jsx";
import Button from "./components/Button.jsx";
import Table from "./components/Table.jsx";
import LoadingState from "./components/LoadingState.jsx";
import ErrorState from "./components/ErrorState.jsx";
import EmptyState from "./components/EmptyState.jsx";
import FormField, { Select } from "./components/FormField.jsx";
import { useToast } from "./components/Toast.jsx";
import { useApiData } from "./useApiData.js";
import { CAN_LAUNCH_PROCESS, hasRole } from "./roles.js";
import { fmtPct, escalationSeverity } from "./format.js";

export default function Processes({ user }) {
  const { data, error, loading, refresh } = useApiData(api.getDashboardSummary);
  const [expanded, setExpanded] = useState(() => new Set());

  function toggle(key) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <>
      {hasRole(user, CAN_LAUNCH_PROCESS) && <LaunchPanel onLaunched={refresh} />}

      <Card
        title="Процессы"
        actions={
          <Button variant="secondary" onClick={refresh}>
            Обновить
          </Button>
        }
      >
        {error ? (
          <ErrorState message={error} onRetry={refresh} />
        ) : loading ? (
          <LoadingState rows={3} />
        ) : !data || data.processes.length === 0 ? (
          <EmptyState message="Нет данных: ни один процесс ещё не запускался." />
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
      </Card>
    </>
  );
}

// E7 — ручной запуск процесса вне расписания Планировщика. process_key —
// строго из серверного реестра (GET /processes, orchestrator/process_registry.py),
// не свободный ввод: клиент не может указать произвольный BPMN-файл.
function LaunchPanel({ onLaunched }) {
  const showToast = useToast();
  const { data } = useApiData(api.listLaunchableProcesses);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const options = data?.processes || [];
  if (!options.length) return null; // реестр пуст — запускать вручную нечего
  const current = selected || options[0].process_key;

  async function launch() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.launchProcess(current);
      showToast(`Запущен новый экземпляр: ${result.case_id}`);
      onLaunched();
    } catch (e) {
      setError(e.message);
      showToast(`Не удалось запустить процесс: ${e.message}`, "critical");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Запустить процесс">
      <div className="flex flex-wrap items-end gap-3">
        <FormField label="Процесс">
          <Select value={current} onChange={(e) => setSelected(e.target.value)}>
            {options.map((p) => (
              <option key={p.process_key} value={p.process_key}>
                {p.process_key}
              </option>
            ))}
          </Select>
        </FormField>
        <Button variant="primary" onClick={launch} busy={busy} busyLabel="Запускаю…">
          Запустить новый экземпляр
        </Button>
      </div>
      {error && <p className="mt-2 text-sm text-status-critical">{error}</p>}
    </Card>
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
    <Table
      columns={["Задача", "Экземпляров", "Вовремя", "Напоминание", "Эскалация", "Доля просрочки", "Доля эскалации"]}
      rows={rows}
      rowKey={(cp) => cp.task}
      renderRow={(cp) => {
        const severity = escalationSeverity(cp.escalated_fraction);
        return (
          <>
            <td className="py-2 pr-3 text-ink dark:text-ink-dark">{cp.task}</td>
            <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">{cp.n_cases}</td>
            <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">{cp.on_time}</td>
            <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">{cp.reminded}</td>
            <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">{cp.escalated}</td>
            <td className="py-2 pr-3 tabular-nums text-ink-secondary dark:text-ink-dark-secondary">
              {fmtPct(cp.late_fraction)}
            </td>
            <td className="py-2">
              {severity && (
                <Badge tone={severity.tone}>
                  {fmtPct(cp.escalated_fraction)} · {severity.label}
                </Badge>
              )}
            </td>
          </>
        );
      }}
    />
  );
}

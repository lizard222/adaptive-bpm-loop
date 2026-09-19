import { useState } from "react";
import * as api from "./api.js";
import StatTile from "./components/StatTile.jsx";
import Badge from "./components/Badge.jsx";
import Card from "./components/Card.jsx";
import Button from "./components/Button.jsx";
import Table from "./components/Table.jsx";
import Pagination from "./components/Pagination.jsx";
import LoadingState from "./components/LoadingState.jsx";
import ErrorState from "./components/ErrorState.jsx";
import EmptyState from "./components/EmptyState.jsx";
import FormField, { Input, Select } from "./components/FormField.jsx";
import { useToast } from "./components/Toast.jsx";
import { useApiData } from "./useApiData.js";
import { useListControls, compareByDate, compareByString } from "./useListControls.js";
import { CAN_LAUNCH_PROCESS, hasRole } from "./roles.js";
import { fmtPct, fmtDate, escalationSeverity } from "./format.js";

// "По умолчанию" — без compare, сохраняет порядок, в котором прислал
// бэкенд (активные → завершённые → алфавит, см. api/dashboard.py).
const SORT_OPTIONS = [
  { key: "default", label: "По умолчанию (активные сначала)" },
  { key: "newest", label: "Сначала новые", compare: compareByDate("last_seen", "desc") },
  { key: "oldest", label: "Сначала старые", compare: compareByDate("first_seen", "asc") },
  { key: "type", label: "По типу процесса (А-Я)", compare: compareByString("process_key", "asc") },
];

function matchesQuery(process, query) {
  return process.process_key.toLowerCase().includes(query);
}

export default function Processes({ user }) {
  const { data, error, loading, refresh } = useApiData(api.getDashboardSummary);
  const [expanded, setExpanded] = useState(() => new Set());
  const { query, setQuery, sortKey, setSortKey, page, setPage, totalPages, totalCount, pageItems, pageSize } =
    useListControls(data?.processes || [], { searchFn: matchesQuery, sortOptions: SORT_OPTIONS, pageSize: 10 });

  function toggle(key) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  // Сортировка "по умолчанию" всегда ставит только что запущенный/активный
  // процесс наверх — но если пользователь до этого пролистал на страницу 2+
  // (искал что-то, разбирал старые смоук-тестовые process_key), новый элемент
  // окажется на первой странице, а пользователь останется там, где был, и
  // просто не увидит его. Поэтому и обычное обновление, и запуск нового
  // процесса возвращают на первую страницу — иначе "процесс не появился в
  // списке" на самом деле означает "появился, но не на той странице".
  function refreshAndResetPage() {
    refresh();
    setPage(1);
  }

  return (
    <>
      {hasRole(user, CAN_LAUNCH_PROCESS) && <LaunchPanel onLaunched={refreshAndResetPage} />}

      <Card
        title="Процессы"
        actions={
          <Button variant="secondary" onClick={refreshAndResetPage}>
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
          <>
            <div className="mb-4 flex flex-wrap items-end gap-3">
              <FormField label="Поиск по ключу процесса">
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="например, vkr_defense"
                  className="sm:w-64"
                />
              </FormField>
              <FormField label="Сортировка">
                <Select value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
                  {SORT_OPTIONS.map((o) => (
                    <option key={o.key} value={o.key}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </FormField>
            </div>

            {totalCount === 0 ? (
              <EmptyState message="Ничего не найдено по этому запросу." />
            ) : (
              <div className="flex flex-col gap-2">
                {pageItems.map((p) => (
                  <ProcessRow
                    key={p.process_key}
                    process={p}
                    isOpen={expanded.has(p.process_key)}
                    onToggle={() => toggle(p.process_key)}
                  />
                ))}
              </div>
            )}
            <Pagination page={page} totalPages={totalPages} totalCount={totalCount} pageSize={pageSize} onChange={setPage} />
          </>
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
                {p.kind === "test" ? " (тест, быстрые таймеры)" : ""}
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
  const { process_key, active_instances, completed_instances, params, latest_report } = process;
  return (
    <div className="rounded-md border border-gridline dark:border-white/10">
      <button onClick={onToggle} className="flex w-full items-center justify-between px-4 py-3 text-left">
        <span className="font-mono text-sm text-ink dark:text-ink-dark">{process_key}</span>
        <span className="flex items-center gap-4 text-xs text-ink-muted">
          <span>{active_instances} активных</span>
          <span>{completed_instances} завершённых</span>
          <span>{fmtPct(latest_report?.fitness) ?? "—"} соответствие</span>
          <span>{isOpen ? "▲" : "▼"}</span>
        </span>
      </button>
      {isOpen && (
        <div className="border-t border-gridline p-4 dark:border-white/10">
          <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
            <StatTile label="Активные экземпляры" value={active_instances} />
            <StatTile label="Завершённые" value={completed_instances} />
            <StatTile
              label="Соответствие модели"
              value={fmtPct(latest_report?.fitness)}
              hint={!latest_report ? "нет анализа" : "fitness — доля журнала, объяснимая моделью"}
            />
            <StatTile
              label="Точность модели"
              value={fmtPct(latest_report?.precision)}
              hint={!latest_report ? "нет анализа" : "precision — модель не допускает лишнего поведения"}
            />
            <StatTile
              label="Параметры"
              value={params ? `${params.reminder_days} / ${params.escalation_days} дн.` : null}
              hint={params ? `версия ${params.version}` : "нет данных"}
            />
          </div>
          {latest_report && latest_report.control_points.length > 0 && (
            <ControlPointsTable rows={latest_report.control_points} />
          )}
          <InstancesTable processKey={process_key} />
        </div>
      )}
    </div>
  );
}

// Дочерний компонент монтируется только когда строка развёрнута (isOpen) —
// значит, запрос уходит только при первом раскрытии конкретной строки, а не
// сразу для всех процессов на странице. Сворачивание/разворачивание заново
// перезапрашивает свежие данные — недорого, т.к. эндпоинт ограничен 50
// последними экземплярами ОДНОГО процесса.
function InstancesTable({ processKey }) {
  const { data, error, loading, refresh } = useApiData(() => api.listProcessInstances(processKey), [processKey]);
  const instances = data?.instances || [];

  return (
    <div className="mt-4 border-t border-gridline pt-4 dark:border-white/10">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Экземпляры (последние {instances.length ? instances.length : ""})
        </h3>
        <Button variant="ghost" onClick={refresh}>
          Обновить
        </Button>
      </div>
      {error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : loading ? (
        <LoadingState rows={2} />
      ) : instances.length === 0 ? (
        <EmptyState message="Нет ни одного экземпляра этого процесса." />
      ) : (
        <Table
          columns={["Case ID", "Статус", "Текущий шаг", "Обновлён"]}
          rows={instances}
          rowKey={(i) => i.case_id}
          renderRow={(i) => (
            <>
              <td className="py-2 pr-3 font-mono text-xs text-ink-muted">{i.case_id}</td>
              <td className="py-2 pr-3">
                <Badge tone={i.status === "active" ? "accent" : "good"}>
                  {i.status === "active" ? "активен" : "завершён"}
                </Badge>
              </td>
              <td className="py-2 pr-3 text-ink dark:text-ink-dark">
                {i.current_tasks.length > 0 ? i.current_tasks.join(", ") : "—"}
              </td>
              <td className="py-2 pr-3 text-xs tabular-nums text-ink-secondary dark:text-ink-dark-secondary">
                {fmtDate(i.updated_at)}
              </td>
            </>
          )}
        />
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

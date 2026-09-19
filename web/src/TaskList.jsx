import { useMemo, useState } from "react";
import * as api from "./api.js";
import Badge from "./components/Badge.jsx";
import Card from "./components/Card.jsx";
import Button from "./components/Button.jsx";
import Table from "./components/Table.jsx";
import Pagination from "./components/Pagination.jsx";
import LoadingState from "./components/LoadingState.jsx";
import ErrorState from "./components/ErrorState.jsx";
import EmptyState from "./components/EmptyState.jsx";
import ConfirmDialog from "./components/ConfirmDialog.jsx";
import FormField, { Input, Select } from "./components/FormField.jsx";
import { useApiData } from "./useApiData.js";
import { useToast } from "./components/Toast.jsx";
import { useListControls, compareByDate, compareByString } from "./useListControls.js";
import { visibleTasks } from "./roleTasks.js";
import { fmtDate } from "./format.js";

const URGENCY_LABEL = { good: "В срок", warning: "Скоро", critical: "Просрочено" };

const ALL_PROCESSES = "__all__";

const SORT_OPTIONS = [
  { key: "default", label: "По умолчанию" },
  { key: "newest", label: "Сначала новые" },
  { key: "oldest", label: "Сначала старые" },
  { key: "due", label: "По сроку (скоро истекает)" },
  { key: "process", label: "По процессу (А-Я)" },
].map((o) => {
  if (o.key === "newest") return { ...o, compare: compareByDate("created_at", "desc") };
  if (o.key === "oldest") return { ...o, compare: compareByDate("created_at", "asc") };
  if (o.key === "due") return { ...o, compare: compareByDate("due_at", "asc") };
  if (o.key === "process") return { ...o, compare: compareByString("process_key", "asc") };
  return o; // "default" — без compare, порядок как пришло от сервера
});

function matchesQuery(task, query) {
  return (
    task.case_id.toLowerCase().includes(query) ||
    task.task_name.toLowerCase().includes(query) ||
    task.process_key.toLowerCase().includes(query)
  );
}

export default function TaskList({ user }) {
  const { data, error, loading, refresh } = useApiData(api.listTasks);
  const [confirmTask, setConfirmTask] = useState(null);
  const [busy, setBusy] = useState(false);
  const [processFilter, setProcessFilter] = useState(ALL_PROCESSES);
  const showToast = useToast();

  // Нормоконтролю показываем только его шаг (roleTasks.js) — временная
  // клиентская замена настоящих BPMN-дорожек, остальные роли видят все
  // READY-задачи без изменений (см. докстринг roleTasks.js).
  const roleTasks = visibleTasks(data?.tasks || [], user.role);

  const processOptions = useMemo(
    () => [...new Set(roleTasks.map((t) => t.process_key))].sort(),
    [roleTasks],
  );
  const filteredTasks = useMemo(
    () => (processFilter === ALL_PROCESSES ? roleTasks : roleTasks.filter((t) => t.process_key === processFilter)),
    [roleTasks, processFilter],
  );

  const { query, setQuery, sortKey, setSortKey, page, setPage, totalPages, totalCount, pageItems, pageSize } =
    useListControls(filteredTasks, { searchFn: matchesQuery, sortOptions: SORT_OPTIONS, pageSize: 10 });

  // Та же ловушка, что чинили на «Процессах»: если пользователь пролистал
  // на страницу 2+ (искал что-то), обычное обновление списка не должно
  // молча оставлять его там же — свежая задача может оказаться на первой
  // странице, а он её не увидит.
  function refreshAndResetPage() {
    refresh();
    setPage(1);
  }

  async function complete() {
    if (!confirmTask) return;
    setBusy(true);
    try {
      await api.completeTask(confirmTask.case_id, confirmTask.task_name);
      showToast(`Задача «${confirmTask.task_name}» выполнена`);
      setConfirmTask(null);
      await refresh();
    } catch (e) {
      showToast(e.message, "critical");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Задачи"
      actions={
        <Button variant="secondary" onClick={refreshAndResetPage}>
          Обновить
        </Button>
      }
    >
      {error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : loading ? (
        <LoadingState rows={4} />
      ) : roleTasks.length === 0 ? (
        <EmptyState message="Нет активных READY-задач." />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <FormField label="Поиск (экземпляр, задача, процесс)">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="например, approve_topics"
                className="sm:w-64"
              />
            </FormField>
            <FormField label="Процесс">
              <Select value={processFilter} onChange={(e) => setProcessFilter(e.target.value)}>
                <option value={ALL_PROCESSES}>Все процессы</option>
                {processOptions.map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </Select>
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
            <EmptyState message="Ничего не найдено по этому запросу/фильтру." />
          ) : (
            <Table
              columns={["Процесс", "Экземпляр", "Задача", "Срок", ""]}
              rows={pageItems}
              rowKey={(t) => `${t.case_id}/${t.task_name}`}
              renderRow={(t) => (
                <>
                  <td className="py-2 pr-3 text-ink dark:text-ink-dark">{t.process_key}</td>
                  <td className="py-2 pr-3 font-mono text-xs tabular-nums text-ink-muted">{t.case_id}</td>
                  <td className="py-2 pr-3 text-ink dark:text-ink-dark">{t.task_name}</td>
                  <td className="py-2 pr-3">
                    {t.due_at ? (
                      <div className="flex items-center gap-2">
                        <span className="text-xs tabular-nums text-ink-secondary dark:text-ink-dark-secondary">
                          {fmtDate(t.due_at)}
                        </span>
                        <Badge tone={t.urgency}>{URGENCY_LABEL[t.urgency] || t.urgency}</Badge>
                      </div>
                    ) : (
                      <span className="text-ink-muted">—</span>
                    )}
                  </td>
                  <td className="py-2">
                    <Button variant="primary" onClick={() => setConfirmTask(t)}>
                      Выполнить
                    </Button>
                  </td>
                </>
              )}
            />
          )}
          <Pagination page={page} totalPages={totalPages} totalCount={totalCount} pageSize={pageSize} onChange={setPage} />
        </>
      )}

      <ConfirmDialog
        open={!!confirmTask}
        title="Завершить задачу?"
        body={confirmTask && `«${confirmTask.task_name}» для экземпляра ${confirmTask.case_id}. Действие необратимо.`}
        confirmLabel="Выполнить"
        busy={busy}
        onConfirm={complete}
        onCancel={() => setConfirmTask(null)}
      />
    </Card>
  );
}

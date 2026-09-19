import { useState } from "react";
import * as api from "./api.js";
import Badge from "./components/Badge.jsx";
import Card from "./components/Card.jsx";
import Button from "./components/Button.jsx";
import Table from "./components/Table.jsx";
import LoadingState from "./components/LoadingState.jsx";
import ErrorState from "./components/ErrorState.jsx";
import EmptyState from "./components/EmptyState.jsx";
import ConfirmDialog from "./components/ConfirmDialog.jsx";
import { useApiData } from "./useApiData.js";
import { useToast } from "./components/Toast.jsx";
import { visibleTasks } from "./roleTasks.js";
import { fmtDate } from "./format.js";

const URGENCY_LABEL = { good: "В срок", warning: "Скоро", critical: "Просрочено" };

export default function TaskList({ user }) {
  const { data, error, loading, refresh } = useApiData(api.listTasks);
  const [confirmTask, setConfirmTask] = useState(null);
  const [busy, setBusy] = useState(false);
  const showToast = useToast();

  // Нормоконтролю показываем только его шаг (roleTasks.js) — временная
  // клиентская замена настоящих BPMN-дорожек, остальные роли видят все
  // READY-задачи без изменений (см. докстринг roleTasks.js).
  const tasks = visibleTasks(data?.tasks || [], user.role);

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
        <Button variant="secondary" onClick={refresh}>
          Обновить
        </Button>
      }
    >
      {error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : loading ? (
        <LoadingState rows={4} />
      ) : tasks.length === 0 ? (
        <EmptyState message="Нет активных READY-задач." />
      ) : (
        <Table
          columns={["Процесс", "Экземпляр", "Задача", "Срок", ""]}
          rows={tasks}
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

import { useEffect, useState } from "react";
import * as api from "./api.js";
import Badge from "./Badge.jsx";
import { fmtDate } from "./format.js";

const URGENCY_LABEL = { good: "В срок", warning: "Скоро", critical: "Просрочено" };

export default function TaskList() {
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState(null);

  async function refresh() {
    try {
      const data = await api.listTasks();
      setTasks(data.tasks);
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

  async function complete(task) {
    const key = `${task.case_id}/${task.task_name}`;
    setBusyKey(key);
    try {
      await api.completeTask(task.case_id, task.task_name);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <section className="rounded-lg border border-gridline bg-surface p-5 dark:border-white/10 dark:bg-surface-dark">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-ink dark:text-ink-dark">Задачи</h2>
        <button
          onClick={refresh}
          className="rounded-md border border-gridline px-3 py-1.5 text-xs font-medium text-ink-secondary hover:bg-page dark:border-white/10 dark:text-ink-dark-secondary dark:hover:bg-white/5"
        >
          Обновить
        </button>
      </div>
      {error && <p className="mb-4 text-sm text-status-critical">{error}</p>}
      {loading ? (
        <p className="py-6 text-center text-sm text-ink-muted">Загрузка задач…</p>
      ) : tasks.length === 0 ? (
        <p className="py-6 text-center text-sm text-ink-muted">Нет активных READY-задач.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gridline text-left text-xs uppercase tracking-wide text-ink-muted dark:border-white/10">
                <th className="py-2 pr-3">Процесс</th>
                <th className="py-2 pr-3">Экземпляр</th>
                <th className="py-2 pr-3">Задача</th>
                <th className="py-2 pr-3">Срок</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => {
                const key = `${t.case_id}/${t.task_name}`;
                return (
                  <tr key={key} className="border-b border-gridline last:border-0 dark:border-white/10">
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
                      <button
                        disabled={busyKey === key}
                        onClick={() => complete(t)}
                        className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:brightness-110 disabled:opacity-60 dark:bg-accent-dark"
                      >
                        {busyKey === key ? "Выполняю…" : "Выполнить"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

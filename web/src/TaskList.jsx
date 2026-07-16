import { useEffect, useState } from "react";
import * as api from "./api.js";

export default function TaskList() {
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState(null);
  const [busyKey, setBusyKey] = useState(null);

  async function refresh() {
    try {
      const data = await api.listTasks();
      setTasks(data.tasks);
      setError(null);
    } catch (e) {
      setError(e.message);
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
    <section className="panel">
      <div className="panel-head">
        <h2>Задачи</h2>
        <button className="ghost" onClick={refresh}>
          Обновить
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {tasks.length === 0 ? (
        <p className="empty">Нет активных READY-задач.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Процесс</th>
              <th>Экземпляр</th>
              <th>Задача</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => {
              const key = `${t.case_id}/${t.task_name}`;
              return (
                <tr key={key}>
                  <td>{t.process_key}</td>
                  <td className="mono">{t.case_id}</td>
                  <td>{t.task_name}</td>
                  <td>
                    <button disabled={busyKey === key} onClick={() => complete(t)}>
                      Выполнить
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

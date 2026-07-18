import { useState } from "react";

export default function Login({ onLogin, error, busy }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function submit(e) {
    e.preventDefault();
    onLogin(username, password);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 dark:bg-page-dark">
      <div className="w-full max-w-sm rounded-lg border border-gridline bg-surface p-8 text-center shadow-sm dark:border-white/10 dark:bg-surface-dark">
        <h1 className="text-lg font-semibold text-ink dark:text-ink-dark">adaptive-bpm-loop</h1>
        <p className="mb-6 mt-1 text-sm text-ink-muted">Кабинет задач и панель корректировок</p>
        <form onSubmit={submit} className="flex flex-col gap-4 text-left">
          <label className="flex flex-col gap-1 text-sm text-ink-secondary dark:text-ink-dark-secondary">
            Логин
            <input
              className="rounded-md border border-gridline bg-page px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-accent dark:border-white/10 dark:bg-page-dark dark:text-ink-dark"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink-secondary dark:text-ink-dark-secondary">
            Пароль
            <input
              type="password"
              className="rounded-md border border-gridline bg-page px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-accent dark:border-white/10 dark:bg-page-dark dark:text-ink-dark"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="mt-1 rounded-md bg-accent py-2 text-sm font-medium text-white hover:brightness-110 disabled:opacity-60 dark:bg-accent-dark"
          >
            {busy ? "Вхожу…" : "Войти"}
          </button>
        </form>
        {error && <p className="mt-4 text-sm text-status-critical">{error}</p>}
        <p className="mt-6 text-xs text-ink-muted">
          Демо-пользователи (api/auth.py): dept_head/dept_head · supervisor/supervisor ·
          secretary/secretary · admin/admin
        </p>
      </div>
    </div>
  );
}

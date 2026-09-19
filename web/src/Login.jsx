import { useState } from "react";
import FormField, { Input } from "./components/FormField.jsx";
import Button from "./components/Button.jsx";

export default function Login({ onLogin, error, busy }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function submit(e) {
    e.preventDefault();
    onLogin(username, password);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 dark:bg-page-dark">
      <div className="w-full max-w-sm rounded-xl border border-gridline bg-surface p-8 text-center shadow-card dark:border-white/10 dark:bg-surface-dark dark:shadow-card-dark">
        <h1 className="text-lg font-semibold text-ink dark:text-ink-dark">adaptive-bpm-loop</h1>
        <p className="mb-6 mt-1 text-sm text-ink-muted">Защита ВКР — кабинет задач и контур адаптации</p>
        <form onSubmit={submit} className="flex flex-col gap-4 text-left">
          <FormField label="Логин">
            <Input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Пароль">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </FormField>
          <Button type="submit" variant="primary" size="md" busy={busy} busyLabel="Вхожу…" className="mt-1">
            Войти
          </Button>
        </form>
        {error && <p className="mt-4 text-sm text-status-critical">{error}</p>}
        <p className="mt-6 text-xs text-ink-muted">
          Демо-пользователи (api/auth.py): dept_head/dept_head · supervisor/supervisor ·
          secretary/secretary · normcontrol/normcontrol · admin/admin
        </p>
      </div>
    </div>
  );
}

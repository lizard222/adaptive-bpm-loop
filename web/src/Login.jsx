import { useState } from "react";

export default function Login({ onLogin, error, busy }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function submit(e) {
    e.preventDefault();
    onLogin(username, password);
  }

  return (
    <div className="login">
      <h1>adaptive-bpm-loop</h1>
      <p className="subtitle">Кабинет задач и панель корректировок</p>
      <form onSubmit={submit}>
        <label>
          Логин
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          Пароль
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Вхожу…" : "Войти"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      <p className="hint">
        Демо-пользователи (api/auth.py): dept_head/dept_head · supervisor/supervisor ·
        secretary/secretary · admin/admin
      </p>
    </div>
  );
}

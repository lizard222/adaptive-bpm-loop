import { useEffect, useState } from "react";
import * as api from "./api.js";
import Login from "./Login.jsx";
import TaskList from "./TaskList.jsx";
import CorrectionsPanel from "./CorrectionsPanel.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loginError, setLoginError] = useState(null);
  const [loginBusy, setLoginBusy] = useState(false);

  useEffect(() => {
    if (!api.getToken()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => api.setToken(null))
      .finally(() => setLoading(false));
  }, []);

  async function handleLogin(username, password) {
    setLoginError(null);
    setLoginBusy(true);
    try {
      await api.login(username, password);
      const u = await api.me();
      setUser(u);
    } catch (e) {
      setLoginError(e.message);
    } finally {
      setLoginBusy(false);
    }
  }

  function handleLogout() {
    api.setToken(null);
    setUser(null);
  }

  if (loading) return <p className="loading">Загрузка…</p>;
  if (!user) return <Login onLogin={handleLogin} error={loginError} busy={loginBusy} />;

  // Панель корректировок (ФТ-С-7.4) — только завкафедрой/администратор,
  // как и на уровне API (require_role в api/corrections.py).
  const canSeeCorrections = user.role === "dept_head" || user.role === "admin";

  return (
    <div className="app">
      <header>
        <h1>adaptive-bpm-loop</h1>
        <div className="user-bar">
          <span>
            {user.full_name} <span className="role">({user.role})</span>
          </span>
          <button className="ghost" onClick={handleLogout}>
            Выйти
          </button>
        </div>
      </header>
      <main>
        <TaskList />
        {canSeeCorrections ? (
          <CorrectionsPanel />
        ) : (
          <section className="panel muted">
            <h2>Корректировки контура адаптации</h2>
            <p className="empty">Доступно только роли «Заведующий кафедрой» и администратору.</p>
          </section>
        )}
      </main>
    </div>
  );
}

import { useEffect, useState } from "react";
import * as api from "./api.js";
import Login from "./Login.jsx";
import Layout from "./Layout.jsx";
import Overview from "./Overview.jsx";
import Processes from "./Processes.jsx";
import TaskList from "./TaskList.jsx";
import Documents from "./Documents.jsx";
import CorrectionsPanel from "./CorrectionsPanel.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loginError, setLoginError] = useState(null);
  const [loginBusy, setLoginBusy] = useState(false);
  const [view, setView] = useState("overview");

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

  if (loading) return <p className="p-10 text-center text-sm text-ink-muted">Загрузка…</p>;
  if (!user) return <Login onLogin={handleLogin} error={loginError} busy={loginBusy} />;

  // Панель корректировок (ФТ-С-7.4) — только завкафедрой/администратор,
  // как и на уровне API (require_role в api/corrections.py). Таб виден
  // всегда — заглушка показывает ограничение явно, а не молча прячет пункт.
  const canSeeCorrections = user.role === "dept_head" || user.role === "admin";

  return (
    <Layout user={user} view={view} onViewChange={setView} onLogout={handleLogout}>
      {view === "overview" && <Overview user={user} onNavigate={setView} />}
      {view === "processes" && <Processes />}
      {view === "tasks" && <TaskList />}
      {view === "documents" && <Documents />}
      {view === "corrections" &&
        (canSeeCorrections ? (
          <CorrectionsPanel />
        ) : (
          <section className="rounded-lg border border-gridline bg-surface p-5 dark:border-white/10 dark:bg-surface-dark">
            <h2 className="mb-2 text-base font-semibold text-ink dark:text-ink-dark">
              Корректировки контура адаптации
            </h2>
            <p className="text-sm text-ink-muted">
              Доступно только роли «Заведующий кафедрой» и администратору.
            </p>
          </section>
        ))}
    </Layout>
  );
}

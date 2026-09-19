import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import * as api from "./api.js";
import Login from "./Login.jsx";
import Layout from "./Layout.jsx";
import Overview from "./Overview.jsx";
import Processes from "./Processes.jsx";
import TaskList from "./TaskList.jsx";
import Documents from "./Documents.jsx";
import CorrectionsPanel from "./CorrectionsPanel.jsx";
import Card from "./components/Card.jsx";
import { CAN_SEE_CORRECTIONS, hasRole } from "./roles.js";

// Тонкий бутстрап: состояние авторизации + маршрутизация (react-router).
// До редизайна здесь был один useState("overview") без URL — обновление
// страницы всегда сбрасывало на "Обзор", back/forward браузера не работал,
// а ролевую проверку для "Корректировки" App.jsx и Overview.jsx дублировали
// каждый по-своему (теперь — единая hasRole() из roles.js).
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

  if (loading) return <p className="p-10 text-center text-sm text-ink-muted">Загрузка…</p>;
  if (!user) return <Login onLogin={handleLogin} error={loginError} busy={loginBusy} />;

  return (
    <Layout user={user} onLogout={handleLogout}>
      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<Overview user={user} />} />
        <Route path="/processes" element={<Processes user={user} />} />
        <Route path="/tasks" element={<TaskList user={user} />} />
        <Route path="/documents" element={<Documents />} />
        <Route
          path="/corrections"
          element={hasRole(user, CAN_SEE_CORRECTIONS) ? <CorrectionsPanel /> : <NoAccess />}
        />
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Routes>
    </Layout>
  );
}

// Пункт меню "Корректировки" теперь скрыт для ролей без доступа (Sidebar.jsx
// фильтрует NAV_ITEMS по roles) — этот экран остаётся как защита при прямом
// переходе по URL, а не единственная линия защиты (ФТ-С-7.4, серверная
// проверка — api/corrections.py::require_role — первична в любом случае).
function NoAccess() {
  return (
    <Card title="Корректировки контура адаптации">
      <p className="text-sm text-ink-muted">Доступно только роли «Заведующий кафедрой» и администратору.</p>
    </Card>
  );
}

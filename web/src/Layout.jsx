import { useLocation } from "react-router-dom";
import Sidebar from "./Sidebar.jsx";

// Заголовок раздела в шапке — раньше Layout.jsx не показывал вообще ничего,
// кроме содержимого экрана (ни хлебных крошек, ни заголовка страницы) —
// один из конкретных источников жалобы "непонятная структура".
const ROUTE_TITLES = {
  "/overview": "Обзор",
  "/processes": "Процессы",
  "/tasks": "Задачи",
  "/documents": "Документы",
  "/corrections": "Корректировки",
};

export default function Layout({ user, onLogout, children }) {
  const location = useLocation();
  const title = ROUTE_TITLES[location.pathname] || "adaptive-bpm-loop";

  return (
    <div className="flex min-h-screen flex-col bg-page dark:bg-page-dark sm:flex-row">
      <Sidebar user={user} onLogout={onLogout} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-gridline bg-surface px-6 py-4 dark:border-white/10 dark:bg-surface-dark">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{title}</h2>
        </header>
        <main className="mx-auto w-full min-w-0 max-w-content flex-1 px-6 py-6">
          <div className="flex flex-col gap-6">{children}</div>
        </main>
      </div>
    </div>
  );
}

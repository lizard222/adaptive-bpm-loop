import { NavLink } from "react-router-dom";
import Button from "./components/Button.jsx";
import { CAN_SEE_CORRECTIONS, hasRole } from "./roles.js";
import { useTheme } from "./useTheme.js";

// roles — необязательно; если не задано, пункт виден всем аутентифицированным
// ролям. "Корректировки" теперь ФИЛЬТРУЕТСЯ здесь, а не просто блокируется на
// уровне контента, как было раньше (пункт был виден всем, но содержимое
// заменялось на "нет доступа" — путало ролей вроде supervisor/secretary).
const NAV_ITEMS = [
  { to: "/overview", label: "Обзор" },
  { to: "/processes", label: "Процессы" },
  { to: "/tasks", label: "Задачи" },
  { to: "/documents", label: "Документы" },
  { to: "/corrections", label: "Корректировки", roles: CAN_SEE_CORRECTIONS },
];

export default function Sidebar({ user, onLogout }) {
  const { theme, toggle } = useTheme();
  const items = NAV_ITEMS.filter((item) => !item.roles || hasRole(user, item.roles));

  return (
    <aside className="flex shrink-0 flex-col gap-4 border-b border-gridline bg-surface p-4 dark:border-white/10 dark:bg-surface-dark sm:min-h-screen sm:w-60 sm:border-b-0 sm:border-r">
      <h1 className="text-lg font-semibold text-ink dark:text-ink-dark">adaptive-bpm-loop</h1>
      <nav className="flex flex-row flex-wrap gap-1 sm:flex-col">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `rounded-md px-3 py-2 text-left text-sm font-medium transition-colors ${
                isActive
                  ? "bg-accent/10 text-accent dark:text-accent-dark"
                  : "text-ink-secondary hover:bg-page dark:text-ink-dark-secondary dark:hover:bg-white/5"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-3 border-t border-gridline pt-4 dark:border-white/10">
        <div className="flex flex-row items-center justify-between gap-3 sm:flex-col sm:items-stretch">
          <span className="text-sm text-ink-secondary dark:text-ink-dark-secondary">
            {user.full_name} <span className="text-xs text-ink-muted">({user.role})</span>
          </span>
          <Button variant="secondary" onClick={onLogout}>
            Выйти
          </Button>
        </div>
        <Button variant="ghost" className="border border-gridline dark:border-white/10" onClick={toggle}>
          {theme === "dark" ? "☀ Светлая тема" : "☾ Тёмная тема"}
        </Button>
      </div>
    </aside>
  );
}

const NAV_ITEMS = [
  { key: "overview", label: "Обзор" },
  { key: "processes", label: "Процессы" },
  { key: "tasks", label: "Задачи" },
  { key: "documents", label: "Документы" },
  { key: "corrections", label: "Корректировки" },
];

export default function Sidebar({ user, view, onViewChange, onLogout }) {
  return (
    <aside className="flex shrink-0 flex-col gap-4 border-b border-gridline bg-surface p-4 dark:border-white/10 dark:bg-surface-dark sm:min-h-screen sm:w-60 sm:border-b-0 sm:border-r">
      <h1 className="text-lg font-semibold text-ink dark:text-ink-dark">adaptive-bpm-loop</h1>
      <nav className="flex flex-row flex-wrap gap-1 sm:flex-col">
        {NAV_ITEMS.map((item) => {
          const active = item.key === view;
          return (
            <button
              key={item.key}
              onClick={() => onViewChange(item.key)}
              className={`rounded-md px-3 py-2 text-left text-sm font-medium transition-colors ${
                active
                  ? "bg-accent/10 text-accent dark:text-accent-dark"
                  : "text-ink-secondary hover:bg-page dark:text-ink-dark-secondary dark:hover:bg-white/5"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </nav>
      <div className="mt-auto flex flex-row items-center justify-between gap-3 border-t border-gridline pt-4 dark:border-white/10 sm:flex-col sm:items-stretch">
        <span className="text-sm text-ink-secondary dark:text-ink-dark-secondary">
          {user.full_name} <span className="text-xs text-ink-muted">({user.role})</span>
        </span>
        <button
          onClick={onLogout}
          className="rounded-md border border-gridline px-3 py-1.5 text-xs font-medium text-ink-secondary hover:bg-page dark:border-white/10 dark:text-ink-dark-secondary dark:hover:bg-white/5"
        >
          Выйти
        </button>
      </div>
    </aside>
  );
}

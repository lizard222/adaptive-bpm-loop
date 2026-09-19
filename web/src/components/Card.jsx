// Заменяет вручную продублированную обёртку
// "rounded-lg border border-gridline bg-surface p-5 dark:..." — до
// редизайна была скопирована буквально в каждый экран (Overview,
// Processes, TaskList, Documents×2, CorrectionsPanel).
export default function Card({ title, actions, children, className = "" }) {
  return (
    <section
      className={`rounded-xl border border-gridline bg-surface p-5 shadow-card dark:border-white/10 dark:bg-surface-dark dark:shadow-card-dark ${className}`}
    >
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold text-ink dark:text-ink-dark">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

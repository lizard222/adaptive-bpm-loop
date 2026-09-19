export default function StatTile({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-gridline bg-surface p-4 shadow-card dark:border-white/10 dark:bg-surface-dark dark:shadow-card-dark">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-ink dark:text-ink-dark">
        {value === null || value === undefined ? "—" : value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-ink-muted">{hint}</div>}
    </div>
  );
}

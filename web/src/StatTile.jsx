export default function StatTile({ label, value, hint }) {
  return (
    <div className="rounded-lg border border-gridline bg-surface p-4 dark:border-white/10 dark:bg-surface-dark">
      <div className="text-xs uppercase tracking-wide text-ink-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-ink dark:text-ink-dark">
        {value === null || value === undefined ? "—" : value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-ink-muted">{hint}</div>}
    </div>
  );
}

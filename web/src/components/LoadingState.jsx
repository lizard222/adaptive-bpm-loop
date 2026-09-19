// Заменяет одинаковый плоский текст "Загрузка…", повторённый в каждом
// экране, скелетоном. Анимация отключается через prefers-reduced-motion
// в style.css.
export default function LoadingState({ rows = 3, label = "Загрузка…" }) {
  return (
    <div className="flex flex-col gap-2 py-1" role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded bg-ink-muted/10"
          style={{ width: `${85 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

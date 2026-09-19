import Button from "./Button.jsx";

// Простая пагинация "назад/вперёд" — при реалистичном для прототипа объёме
// данных (десятки-сотни строк) нумерованные кнопки страниц избыточны.
export default function Pagination({ page, totalPages, totalCount, pageSize, onChange }) {
  if (totalPages <= 1) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, totalCount);
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-gridline pt-3 dark:border-white/10">
      <span className="text-xs text-ink-muted">
        {from}–{to} из {totalCount}
      </span>
      <div className="flex items-center gap-2">
        <Button variant="secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Назад
        </Button>
        <span className="text-xs tabular-nums text-ink-muted">
          {page} / {totalPages}
        </span>
        <Button variant="secondary" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
          Вперёд
        </Button>
      </div>
    </div>
  );
}

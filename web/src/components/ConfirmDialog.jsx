import Button from "./Button.jsx";

// Перед необратимыми действиями (завершение задачи, принятие/отклонение
// корректировки) — до редизайна они срабатывали мгновенно по одному клику.
// Контролируемый компонент: экран сам хранит {open, ...} в своём состоянии
// и решает, когда открыть/закрыть — здесь нет глобального singleton'а.
export default function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Подтвердить",
  confirmVariant = "primary",
  busy = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm rounded-xl border border-gridline bg-surface p-5 shadow-popover dark:border-white/10 dark:bg-surface-dark"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">{title}</h3>
        {body && <p className="mt-2 text-sm text-ink-secondary dark:text-ink-dark-secondary">{body}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Отмена
          </Button>
          <Button variant={confirmVariant} onClick={onConfirm} busy={busy} busyLabel="…">
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

// Варианты покрывают все кнопки, которые раньше были построчно
// продублированы (accent-заливка, зелёная/красная для принять/отклонить,
// рамка для второстепенных действий, текстовая для отмены в диалогах).
const VARIANT_CLASSES = {
  primary: "bg-accent text-white hover:brightness-110 dark:bg-accent-dark",
  secondary:
    "border border-gridline text-ink-secondary hover:bg-page dark:border-white/10 dark:text-ink-dark-secondary dark:hover:bg-white/5",
  success: "bg-status-good text-white hover:brightness-110",
  danger: "bg-status-critical text-white hover:brightness-110",
  ghost: "text-ink-secondary hover:bg-page dark:text-ink-dark-secondary dark:hover:bg-white/5",
};

// "sm" покрывает почти все кнопки приложения (таблицы, карточки); "md" — для
// редких заметных CTA (вход в систему). Через className нельзя надёжно
// перебить py/text-размер той же утility-специфичности — победитель зависит
// от порядка правил в СГЕНЕРИРОВАННОМ CSS, а не от порядка классов в JSX.
const SIZE_CLASSES = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
};

// Экспортируется отдельно, чтобы те же классы можно было применить к
// не-<button> элементу (например, <Link> из react-router — навигационные
// "кнопки" на Overview.jsx семантически являются ссылками, не действиями).
export function buttonClass(variant = "secondary", size = "sm", className = "") {
  return `rounded-md font-medium transition-colors disabled:opacity-60 ${SIZE_CLASSES[size] || SIZE_CLASSES.sm} ${
    VARIANT_CLASSES[variant] || VARIANT_CLASSES.secondary
  } ${className}`;
}

export default function Button({
  variant = "secondary",
  size = "sm",
  busy = false,
  busyLabel,
  children,
  className = "",
  disabled,
  ...props
}) {
  return (
    <button disabled={disabled || busy} className={buttonClass(variant, size, className)} {...props}>
      {busy ? busyLabel || "…" : children}
    </button>
  );
}

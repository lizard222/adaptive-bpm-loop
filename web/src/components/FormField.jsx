// Заменяет продублированные блоки
// "<label className='text-xs text-ink-muted'>...<input className='mt-1 w-full rounded-md ...'>"
// (Documents.jsx, Login.jsx).
const fieldClass =
  "mt-0.5 w-full rounded-md border border-gridline bg-page px-2.5 py-1.5 text-sm text-ink " +
  "focus:outline-none focus:ring-2 focus:ring-accent dark:border-white/10 dark:bg-page-dark dark:text-ink-dark";

export default function FormField({ label, children }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-ink-muted">
      {label}
      {children}
    </label>
  );
}

export function Input(props) {
  return <input className={fieldClass} {...props} />;
}

export function Select({ children, ...props }) {
  return (
    <select className={fieldClass} {...props}>
      {children}
    </select>
  );
}

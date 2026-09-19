import { createContext, useCallback, useContext, useState } from "react";

// Обратная связь по успеху мутаций — до редизайна её не было нигде,
// пользователь мог судить об успехе только по тому, что список сам
// обновился. Простой контекст без внешней библиотеки (toast-набор для
// прототипа маленький — 4 мутации во всём приложении).
const ToastContext = createContext(null);
let idCounter = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, tone = "good") => {
    const id = ++idCounter;
    setToasts((prev) => [...prev, { id, message, tone }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={`pointer-events-auto rounded-lg border px-4 py-2 text-sm shadow-popover ${
              t.tone === "critical"
                ? "border-status-critical/30 bg-surface text-status-critical dark:border-status-critical/40 dark:bg-surface-dark"
                : "border-status-good/30 bg-surface text-status-good dark:border-status-good/40 dark:bg-surface-dark"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast() должен вызываться внутри <ToastProvider>");
  return ctx;
}

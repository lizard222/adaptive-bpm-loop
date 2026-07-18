export function fmtPct(v) {
  return v === null || v === undefined ? null : `${Math.round(v * 100)}%`;
}

export function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

// Прототипные пороги — не откалиброваны по реальным данным кафедры, служат
// только для наглядности на дашборде.
export function escalationSeverity(fraction) {
  if (fraction === null || fraction === undefined) return null;
  if (fraction < 0.05) return { tone: "good", label: "Хорошо" };
  if (fraction < 0.15) return { tone: "warning", label: "Внимание" };
  if (fraction < 0.3) return { tone: "serious", label: "Серьёзно" };
  return { tone: "critical", label: "Критично" };
}

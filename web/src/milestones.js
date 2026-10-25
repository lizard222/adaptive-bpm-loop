// Ключевые даты защиты (E14): предзащита и защита конкретного студента.
// Поле <input type="datetime-local"> работает в местном времени браузера и без
// часового пояса, а сервер требует ISO с поясом — переводим в обе стороны здесь.

export const MILESTONE_LABELS = { predefense_at: "Предзащита", defense_at: "Защита" };

export function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromLocalInput(value) {
  return value ? new Date(value).toISOString() : null;
}

export function milestonesFromInputs(inputs) {
  return {
    predefense_at: fromLocalInput(inputs.predefense_at),
    defense_at: fromLocalInput(inputs.defense_at),
  };
}

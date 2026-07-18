// Метки времени в event_log/process_instances могут быть "из будущего"
// относительно реального часов — simgen прогоняет эксперименты под
// управляемым временем (freezegun), и ts пишется явно из симулированного
// datetime.now() (см. B5-находку: событие должно отражать виртуальное время
// цикла, не серверное). На честном рабочем экране это НЕ означает "агент
// только что сработал" — это старые синтетические данные с датой в будущем,
// нужно показать как есть, а не выдавать за недавнюю активность.
function minutesAgo(iso) {
  return (Date.now() - new Date(iso).getTime()) / 60000;
}

export function relativeTime(iso) {
  if (!iso) return "ещё не работал";
  const minutes = minutesAgo(iso);
  if (minutes < 0) return `дата в будущем (синт. данные, ${new Date(iso).toLocaleDateString("ru-RU")})`;
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${Math.floor(minutes)} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} дн назад`;
  return "давно";
}

export function agentTone(iso) {
  if (!iso) return "neutral";
  const minutes = minutesAgo(iso);
  if (minutes < 0) return "neutral"; // дата в будущем — не признак реальной недавней активности
  if (minutes < 15) return "good";
  if (minutes < 24 * 60) return "warning";
  return "neutral"; // "давно" — не обязательно плохо, просто не недавно
}

// Единый словарь тонов для Badge и StatusDot. До редизайна у них были
// РАЗНЫЕ наборы (Badge: good|warning|serious|critical|accent|neutral;
// StatusDot: good|warning|critical|neutral — без serious/accent), из-за
// чего одну и ту же семантику нельзя было одинаково раскрасить в обоих
// местах. Семантические тона (good/warning/serious/critical) — не accent
// приложения, они отдельная шкала состояния.
export const TONE_BADGE_CLASSES = {
  good: "bg-status-good/10 text-status-good",
  warning: "bg-status-warning/10 text-status-warning",
  serious: "bg-status-serious/10 text-status-serious",
  critical: "bg-status-critical/10 text-status-critical",
  accent: "bg-accent/10 text-accent dark:text-accent-dark",
  neutral: "bg-ink-muted/10 text-ink-muted",
};

export const TONE_DOT_CLASSES = {
  good: "bg-status-good",
  warning: "bg-status-warning",
  serious: "bg-status-serious",
  critical: "bg-status-critical",
  accent: "bg-accent dark:bg-accent-dark",
  neutral: "bg-ink-muted",
};

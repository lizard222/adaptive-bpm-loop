const TONE_CLASSES = {
  good: "bg-status-good/10 text-status-good",
  warning: "bg-status-warning/10 text-status-warning",
  serious: "bg-status-serious/10 text-status-serious",
  critical: "bg-status-critical/10 text-status-critical",
  accent: "bg-accent/10 text-accent dark:text-accent-dark",
  neutral: "bg-ink-muted/10 text-ink-muted",
};

export default function Badge({ tone = "neutral", children }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone] || TONE_CLASSES.neutral}`}
    >
      {children}
    </span>
  );
}

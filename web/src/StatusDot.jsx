const DOT_CLASSES = {
  good: "bg-status-good",
  warning: "bg-status-warning",
  critical: "bg-status-critical",
  neutral: "bg-ink-muted",
};

export default function StatusDot({ tone = "neutral" }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${DOT_CLASSES[tone] || DOT_CLASSES.neutral}`} />;
}

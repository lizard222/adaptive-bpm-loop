import { TONE_BADGE_CLASSES } from "./tones.js";

export default function Badge({ tone = "neutral", children }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_BADGE_CLASSES[tone] || TONE_BADGE_CLASSES.neutral}`}
    >
      {children}
    </span>
  );
}

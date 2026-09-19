import { TONE_DOT_CLASSES } from "./tones.js";

export default function StatusDot({ tone = "neutral" }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${TONE_DOT_CLASSES[tone] || TONE_DOT_CLASSES.neutral}`} />;
}

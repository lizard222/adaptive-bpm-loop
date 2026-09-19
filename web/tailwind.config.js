/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  // Было "media" (только системная тема) — редизайн добавляет ручной
  // переключатель (useTheme.js, класс "dark" на <html>), поэтому темизация
  // теперь управляется классом, а не только media-запросом.
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Палитра ниже НЕ меняется при редизайне: accent/status уже
        // провалидированы через dataviz-скилл и переиспользуются в
        // experiment/plots.py (графики главы 4 диссертации) — смена цветов
        // здесь разошлась бы с уже готовыми иллюстрациями работы.
        accent: { DEFAULT: "#2a78d6", dark: "#3987e5" },
        status: {
          good: "#0ca30c",
          warning: "#fab219",
          serious: "#ec835a",
          critical: "#d03b3b",
        },
        surface: { DEFAULT: "#fcfcfb", dark: "#1a1a19" },
        page: { DEFAULT: "#f9f9f7", dark: "#0d0d0d" },
        ink: {
          DEFAULT: "#0b0b0b",
          secondary: "#52514e",
          muted: "#898781",
          dark: "#ffffff",
          "dark-secondary": "#c3c2b7",
        },
        gridline: "#e1e0d9",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.5rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem" }],
        "2xl": ["1.5rem", { lineHeight: "2rem" }],
      },
      spacing: {
        4.5: "1.125rem",
        13: "3.25rem",
        18: "4.5rem",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.25rem",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 3px 0 rgb(0 0 0 / 0.06)",
        "card-dark": "0 1px 2px 0 rgb(0 0 0 / 0.3), 0 1px 3px 0 rgb(0 0 0 / 0.4)",
        popover: "0 4px 16px -2px rgb(0 0 0 / 0.12)",
      },
      maxWidth: {
        content: "72rem",
      },
    },
  },
  plugins: [],
};

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
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
        sans: ["system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
      },
    },
  },
  plugins: [],
};

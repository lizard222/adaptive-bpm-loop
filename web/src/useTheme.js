import { useEffect, useState } from "react";

const STORAGE_KEY = "abl_theme"; // "light" | "dark"

function systemPrefersDark() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function readStoredTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // приватный режим/заблокированное хранилище — не должно ронять UI
  }
}

function applyTheme(theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

// Ручной переключатель темы (redesign): раньше darkMode:"media" следовал
// только системной настройке без возможности переопределить. Выбор
// пользователя хранится в localStorage и переживает перезагрузку; при
// первом визите (нет сохранённого значения) — используется системная тема,
// как и раньше.
export function useTheme() {
  const [theme, setTheme] = useState(() => readStoredTheme() || (systemPrefersDark() ? "dark" : "light"));

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  function toggle() {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* игнорируем — тема просто не переживёт перезагрузку в этой сессии */
      }
      return next;
    });
  }

  return { theme, toggle };
}

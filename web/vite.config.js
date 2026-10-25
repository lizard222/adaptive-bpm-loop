import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Прокси на локальный API (uvicorn api.main:app, порт 8000) — не нужен CORS
// на бэкенде для dev-режима. Продовая раздача собранного билда за реальным
// реверс-прокси/CORS — вне объёма прототипа (T-37).
//
// Префиксы API совпадают с адресами экранов (/processes, /tasks, /documents):
// без bypass обновление страницы (F5) или открытие ссылки на экран уводило
// запрос браузера за HTML на бэкенд, и вместо экрана показывался JSON
// {"detail":"Not authenticated"}. Запросы страниц (Accept: text/html) отдаёт
// сам Vite — приложение, а fetch из api.js по-прежнему идёт на API.
const API = "http://localhost:8000";
const api = {
  target: API,
  bypass(req) {
    if (req.headers.accept?.includes("text/html")) return "/index.html";
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": api,
      "/tasks": api,
      "/corrections": api,
      "/dashboard": api,
      "/documents": api,
      "/processes": api,
      "/me": api,
      "/cases": api,
    },
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Прокси на локальный API (uvicorn api.main:app, порт 8000) — не нужен CORS
// на бэкенде для dev-режима. Продовая раздача собранного билда за реальным
// реверс-прокси/CORS — вне объёма прототипа (T-37).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8000",
      "/tasks": "http://localhost:8000",
      "/corrections": "http://localhost:8000",
      "/me": "http://localhost:8000",
    },
  },
});

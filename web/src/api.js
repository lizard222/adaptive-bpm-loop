// Тонкий клиент к api/ (T-30 авторизация, T-37 задачи/корректировки).
// Токен — в localStorage; в проде так делать не стоит (XSS), но для
// прототипа с демо-пользователями это осознанное упрощение.
const TOKEN_KEY = "abl_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail && typeof body.detail === "object" && Array.isArray(body.detail.missing_fields)) {
        detail = `не хватает полей: ${body.detail.missing_fields.join(", ")}`;
      } else {
        detail = body.detail || detail;
      }
    } catch {
      /* тело не JSON — оставляем statusText */
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

export async function login(username, password) {
  const body = new URLSearchParams();
  body.set("username", username);
  body.set("password", password);
  const res = await fetch("/auth/token", { method: "POST", body });
  if (!res.ok) throw new Error("Неверный логин или пароль");
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

export function me() {
  return request("/me");
}

export function listTasks() {
  return request("/tasks");
}

export function completeTask(caseId, taskName, data = {}) {
  return request(`/tasks/${encodeURIComponent(caseId)}/${encodeURIComponent(taskName)}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function listPendingCorrections() {
  return request("/corrections/pending");
}

export function decideCorrection(id, decision) {
  return request(`/corrections/${id}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
}

export function getDashboardSummary() {
  return request("/dashboard/summary");
}

export function listDocumentTemplates() {
  return request("/documents/templates");
}

export function generateDocument(payload) {
  return request("/documents/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function listDocuments() {
  return request("/documents");
}

// Простая ссылка <a href> не понесёт токен — авторизация только через JS
// fetch с Bearer-заголовком (см. комментарий вверху файла), не куки.
export async function downloadDocument(id, suggestedFilename) {
  const token = getToken();
  const res = await fetch(`/documents/${id}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Не удалось скачать документ");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = suggestedFilename || `document_${id}.docx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

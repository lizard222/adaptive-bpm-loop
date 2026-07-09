"""Каркас API (T-30): здоровье инфраструктуры, JWT-авторизация, ролевой доступ.

Запуск локально:  uvicorn api.main:app --reload
Инфраструктура:   docker compose up -d   (PostgreSQL + Redis)
"""
import psycopg
import redis as redis_lib
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from .auth import CurrentUser, authenticate, create_token, get_current_user, require_role
from .config import settings

app = FastAPI(
    title="adaptive-bpm-loop",
    description="Адаптивное управление бизнес-процессами вуза: каркас прототипа",
    version="0.1.0",
)


@app.get("/", tags=["service"])
def root():
    return {"service": "adaptive-bpm-loop", "version": app.version}


@app.get("/health", tags=["service"])
def health():
    """Проверка инфраструктуры: PostgreSQL и Redis (используется в NFR-5 проверке развёртывания)."""
    result = {"api": "ok"}
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM event_log")
                result["postgres"] = f"ok (event_log: {cur.fetchone()[0]} записей)"
    except Exception as exc:  # noqa: BLE001 — health должен отвечать всегда
        result["postgres"] = f"fail: {exc}"
    try:
        r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=3)
        r.ping()
        result["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        result["redis"] = f"fail: {exc}"
    return result


@app.post("/auth/token", tags=["auth"])
def issue_token(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate(form.username, form.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")
    return {"access_token": create_token(form.username, user["role"]), "token_type": "bearer"}


@app.get("/me", tags=["auth"])
def me(user: CurrentUser = Depends(get_current_user)):
    return user


@app.get("/admin/ping", tags=["demo"])
def admin_ping(user: CurrentUser = Depends(require_role("admin"))):
    """Демонстрация ролевого доступа: только администратор."""
    return {"ok": True, "you": user.username}


@app.get("/corrections/pending", tags=["demo"])
def corrections_pending(user: CurrentUser = Depends(require_role("dept_head", "admin"))):
    """Заглушка панели корректировок (ФТ-С-7.4): доступна завкафедрой и администратору.
    Наполнение — после реализации Аналитика-Адаптера (T-42)."""
    return {"pending": [], "note": "контур адаптации ещё не реализован (T-42)"}

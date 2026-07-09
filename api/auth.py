"""JWT-авторизация по ролям (НФТ-8).

Паттерн, заимствованный из TRACE: роли пользователей = авторизация ДО оркестратора
(здесь, на уровне API); роли агентов = оркестрация ВНУТРИ (слой агентов, не здесь).
"""
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from .config import settings

# Роли пользователей системы (раздел 1.4 документа требований)
ROLES = ("dept_head", "supervisor", "secretary", "normcontrol", "student", "admin")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


def _h(password: str) -> str:
    # Для прототипа достаточно sha256; в продуктивной системе — bcrypt/argon2
    return hashlib.sha256(password.encode()).hexdigest()


# Демо-пользователи каркаса. Реальный справочник пользователей — вместе со схемой БД (T-25).
DEMO_USERS = {
    "dept_head": {"password": _h("dept_head"), "role": "dept_head", "full_name": "Заведующий кафедрой (демо)"},
    "supervisor": {"password": _h("supervisor"), "role": "supervisor", "full_name": "Руководитель ВКР (демо)"},
    "secretary": {"password": _h("secretary"), "role": "secretary", "full_name": "Секретарь кафедры (демо)"},
    "admin": {"password": _h("admin"), "role": "admin", "full_name": "Администратор (демо)"},
}


class CurrentUser(BaseModel):
    username: str
    role: str
    full_name: str


def authenticate(username: str, password: str) -> dict | None:
    user = DEMO_USERS.get(username)
    if user is None or user["password"] != _h(password):
        return None
    return user


def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    username = payload.get("sub", "")
    user = DEMO_USERS.get(username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return CurrentUser(username=username, role=payload.get("role", ""), full_name=user["full_name"])


def require_role(*allowed: str):
    """Зависимость FastAPI: доступ только перечисленным ролям (ФТ-А-И-3)."""

    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Роль '{user.role}' не имеет доступа; требуется: {', '.join(allowed)}",
            )
        return user

    return checker

"""后台用户登录路由测试。"""

import hashlib
import os
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.auth as auth_module
from lib.db.models.user import User
from server.routers import users as users_router


class _FakeResult:
    def __init__(self, user: User | None):
        self._user = user

    def scalar_one_or_none(self) -> User | None:
        return self._user


class _FakeSession:
    def __init__(self, user: User | None):
        self._user = user

    async def execute(self, _statement):
        return _FakeResult(self._user)

    async def commit(self):
        pass


def test_default_admin_can_login_when_legacy_row_has_no_password_hash():
    """迁移遗留的 default 用户没有密码哈希时，仍沿用运行时管理员凭据登录。"""
    user = User(id=1, username="admin", role="admin", is_active=True, hashed_password=None)
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api/v1")

    async def override_get_session():
        yield _FakeSession(user)

    app.dependency_overrides[users_router.get_session] = override_get_session
    auth_module._cached_password_hash = None

    with patch.dict(
        os.environ,
        {
            "AUTH_USERNAME": "admin",
            "AUTH_PASSWORD": "admin123",
            "AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes-long",
        },
    ):
        with TestClient(app) as client:
            response = client.post("/api/v1/users/login", json={"username": "admin", "password": "admin123"})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_legacy_sha256_admin_can_login_and_hash_is_upgraded():
    """脚本遗留的 SHA-256 管理员密码可登录，并升级为 pwdlib 哈希。"""
    user = User(
        id=2,
        username="root",
        role="admin",
        is_active=True,
        hashed_password=hashlib.sha256(b"root123").hexdigest(),
    )
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api/v1")

    async def override_get_session():
        yield _FakeSession(user)

    app.dependency_overrides[users_router.get_session] = override_get_session

    with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret-key-that-is-at-least-32-bytes-long"}):
        with TestClient(app) as client:
            response = client.post("/api/v1/users/login", json={"username": "root", "password": "root123"})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert user.hashed_password is not None
    assert user.hashed_password.startswith("$argon2")

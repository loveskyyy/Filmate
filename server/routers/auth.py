"""
认证 API 路由

提供 OAuth2 登录和 token 验证接口。
"""

import logging
import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.engine import get_async_session
from lib.i18n import Translator
from server.auth import (
    CurrentUser,
    check_credentials,
    create_token,
    is_auth_enabled,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 响应模型 ====================


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class VerifyResponse(BaseModel):
    valid: bool
    username: str


class AuthStatusResponse(BaseModel):
    enabled: bool


# ==================== 路由 ====================


@router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status():
    """暴露 ``AUTH_ENABLED`` 状态供前端 bootstrap 判断是否需要登录拦截。

    前端 ``auth-store.initialize()`` 在 localStorage 无 token 时调用本接口：
    ``enabled=false`` 时跳过登录页直接进主界面；``enabled=true`` 时保留原
    登录链路。本接口本身**不要求认证**——一个 boolean 比 401 探针更直观，
    且实际"是否需要登录"通过 401/200 也能从外部观察到，因此不增量泄露。
    """
    return AuthStatusResponse(enabled=is_auth_enabled())


@router.post("/auth/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    _t: Translator,
    session: AsyncSession = Depends(get_async_session),
):
    """用户登录

    使用 OAuth2 标准表单格式验证凭据，成功返回 access_token。
    ``AUTH_ENABLED=false`` 时跳过凭据校验，直接签发 token，让前端
    LoginPage 即便被打开也能正常跳转主界面。
    """
    if is_auth_enabled() and not await check_credentials(form_data.username, form_data.password, session):
        logger.warning("登录失败: 用户名或密码错误 (用户: %s)", form_data.username)
        raise HTTPException(
            status_code=401,
            detail=_t("unauthorized"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    from lib.db.base import DEFAULT_USER_ID

    expected_username = os.environ.get("AUTH_USERNAME", "admin")
    if not is_auth_enabled() or secrets.compare_digest(form_data.username, expected_username):
        user_id = DEFAULT_USER_ID
        role = "admin"
    else:
        from sqlalchemy import select

        from lib.db.models.user import User

        result = await session.execute(select(User).where(User.username == form_data.username))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail=_t("unauthorized"))
        user_id = user.id
        role = user.role
    token = create_token(form_data.username, user_id=user_id, role=role)
    logger.info("用户登录成功: %s", form_data.username)
    return TokenResponse(access_token=token, token_type="bearer")


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


class RegisterResponse(BaseModel):
    success: bool
    message: str
    user_id: int | None = None


@router.post("/auth/register", response_model=RegisterResponse)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """用户注册

    创建新用户账号。
    """
    from sqlalchemy import select

    from lib.db.models.user import User
    from server.auth import _password_hash

    # 验证用户名和密码
    if not body.username or len(body.username) < 3:
        raise HTTPException(status_code=400, detail="用户名至少3个字符")
    if not body.password or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6个字符")

    # 检查用户名是否已存在
    result = await session.execute(select(User).where(User.username == body.username))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 创建新用户
    new_user = User(
        username=body.username,
        email=body.email,
        hashed_password=_password_hash.hash(body.password),
        role="user",
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    logger.info("用户注册成功: %s", body.username)
    return RegisterResponse(
        success=True,
        message="注册成功",
        user_id=new_user.id,
    )


@router.get("/auth/verify", response_model=VerifyResponse)
async def verify(
    current_user: CurrentUser,
):
    """验证 token 有效性

    使用 OAuth2 Bearer token 依赖自动提取和验证 token。
    """
    return VerifyResponse(valid=True, username=current_user.sub)

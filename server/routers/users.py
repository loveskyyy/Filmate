"""用户管理 API"""

import hashlib
import hmac
import string
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lib.db import async_engine
from lib.db.models.user import User
from server.auth import _password_hash, check_credentials, create_token

router = APIRouter()

# 创建 session 依赖
_async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _async_session_factory() as session:
        yield session


def make_hash(password: str) -> str:
    return _password_hash.hash(password)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str | None = None
    role: str
    is_active: bool
    credits: int
    created_at: str | None = None
    updated_at: str | None = None


class UserCreate(BaseModel):
    username: str
    email: str | None = None
    password: str
    role: str = "user"
    credits: int = 0


class UserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None
    credits: int | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


# 重要：/users/login 必须在 /users/{user_id} 之前定义
@router.post("/users/login")
async def login(data: LoginRequest, session: AsyncSession = Depends(get_session)):
    """用户登录"""
    result = await session.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # `default` 用户由旧版迁移创建时没有密码字段；兼容主认证链路中的
    # AUTH_USERNAME/AUTH_PASSWORD，避免把 NULL 传给 pwdlib 导致 500。
    # 初始化脚本早期使用 SHA-256，成功登录后升级为 pwdlib 哈希。
    legacy_hash = user.hashed_password
    should_upgrade_hash = legacy_hash is None
    if legacy_hash is None:
        password_ok = check_credentials(data.username, data.password)
    elif len(legacy_hash) == 64 and all(char in string.hexdigits for char in legacy_hash):
        expected_legacy_hash = hashlib.sha256(data.password.encode("utf-8")).hexdigest()
        password_ok = hmac.compare_digest(expected_legacy_hash, legacy_hash)
        should_upgrade_hash = password_ok
    else:
        password_ok = _password_hash.verify(data.password, legacy_hash)
    if not password_ok:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if should_upgrade_hash:
        user.hashed_password = _password_hash.hash(data.password)
        await session.commit()

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员才能登录后台")

    token = create_token(data.username)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/users", response_model=list[UserResponse])
async def list_users(session: AsyncSession = Depends(get_session)):
    """获取用户列表"""
    result = await session.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            credits=u.credits,
            created_at=u.created_at.isoformat() if u.created_at else None,
            updated_at=u.updated_at.isoformat() if u.updated_at else None,
        )
        for u in users
    ]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)):
    """获取用户"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        credits=user.credits,
        created_at=user.created_at.isoformat() if user.created_at else None,
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
    )


@router.post("/users", response_model=UserResponse)
async def create_user(data: UserCreate, session: AsyncSession = Depends(get_session)):
    """创建用户"""
    result = await session.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    if data.email:
        result = await session.execute(select(User).where(User.email == data.email))
        if result.first():
            raise HTTPException(status_code=400, detail="邮箱已被使用")

    hashed = make_hash(data.password)
    user = User(username=data.username, email=data.email, hashed_password=hashed, role=data.role, credits=data.credits)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        credits=user.credits,
        created_at=user.created_at.isoformat() if user.created_at else None,
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, data: UserUpdate, session: AsyncSession = Depends(get_session)):
    """更新用户"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if data.username is not None and data.username != user.username:
        result = await session.execute(select(User).where(User.username == data.username))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="用户名已存在")
        user.username = data.username

    if data.email is not None and data.email != "":
        result = await session.execute(select(User).where(User.email == data.email, User.id != user_id))
        if result.first():
            raise HTTPException(status_code=400, detail="邮箱已被使用")
        user.email = data.email

    if data.password is not None:
        user.hashed_password = make_hash(data.password)

    if data.role is not None:
        user.role = data.role

    if data.is_active is not None:
        user.is_active = data.is_active

    if data.credits is not None:
        user.credits = data.credits

    await session.commit()
    await session.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        credits=user.credits,
        created_at=user.created_at.isoformat() if user.created_at else None,
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
    )


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, session: AsyncSession = Depends(get_session)):
    """删除用户"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    await session.delete(user)
    await session.commit()
    return {"deleted": user_id}


class CreditsAdjustRequest(BaseModel):
    amount: int
    reason: str | None = None


@router.post("/users/{user_id}/credits", response_model=UserResponse)
async def adjust_user_credits(user_id: int, data: CreditsAdjustRequest, session: AsyncSession = Depends(get_session)):
    """调整用户积分"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    new_credits = user.credits + data.amount
    if new_credits < 0:
        raise HTTPException(status_code=400, detail="积分不足，无法减少")

    user.credits = new_credits
    await session.commit()
    await session.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        credits=user.credits,
        created_at=user.created_at.isoformat() if user.created_at else None,
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
    )

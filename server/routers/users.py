"""用户管理 API"""

import hashlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db import async_session_factory
from lib.db.models.user import User
from server.auth import check_credentials, create_token

router = APIRouter()


def make_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


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


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


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
    # 检查用户名是否已存在
    result = await session.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 检查邮箱是否已存在
    if data.email:
        result = await session.execute(select(User).where(User.email == data.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="邮箱已被使用")

    hashed = make_hash(data.password)
    user = User(username=data.username, email=data.email, hashed_password=hashed, role=data.role)
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
        # 检查新用户名是否已存在
        result = await session.execute(select(User).where(User.username == data.username))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="用户名已存在")
        user.username = data.username

    if data.email is not None:
        result = await session.execute(select(User).where(User.email == data.email, User.id != user_id))
        if result.scalar_one_or_none():
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


@router.post("/users/login")
async def login(data: LoginRequest):
    """用户登录"""
    if not check_credentials(data.username, data.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(data.username)
    return {"access_token": token, "token_type": "bearer"}

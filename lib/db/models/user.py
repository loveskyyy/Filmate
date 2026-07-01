"""User model for multi-user infrastructure."""

import secrets

import sqlalchemy as sa
from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="user")  # admin / user
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sa.true())
    credits: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # 积分

    @staticmethod
    def generate_id() -> str:
        """生成唯一 ID（保留兼容）"""
        return secrets.token_hex(8)

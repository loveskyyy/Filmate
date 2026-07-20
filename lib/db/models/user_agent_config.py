"""用户智能体配置 ORM 模型。

每个用户可以配置多个智能体供应商，字段与 custom_provider 一致，额外添加 user_id。
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin


class UserAgentConfig(TimestampMixin, Base):
    """用户智能体配置。"""

    __tablename__ = "user_agent_config"
    __table_args__ = (
        Index("ix_user_agent_config_user_id", "user_id"),
        Index("ix_user_agent_config_user_discovery", "user_id", "discovery_format"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # 显示名称
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)

    # 供应商格式 (openai / google)
    discovery_format: Mapped[str] = mapped_column(String(32), nullable=False)

    # API 配置
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)  # sensitive, masked in API responses

    # 并发上限制
    image_max_workers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_max_workers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_max_workers: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 模型配置
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 价格配置
    price_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    price_input: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_output: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # 是否启用
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 扩展配置（JSON 格式）
    extra_config: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserAgentPreset(TimestampMixin, Base):
    """用户智能体预设模板。"""

    __tablename__ = "user_agent_preset"
    __table_args__ = (Index("ix_user_agent_preset_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # 预设名称
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # 供应商
    provider: Mapped[str] = mapped_column(String(64), nullable=False)

    # 模型
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    # 系统提示词
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 其他配置
    config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

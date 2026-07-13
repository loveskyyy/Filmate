"""User Agent Config Repository."""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.models.user_agent_config import UserAgentConfig, UserAgentPreset


class UserAgentConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(self, user_id: int) -> Sequence[UserAgentConfig]:
        result = await self.session.execute(
            select(UserAgentConfig).where(UserAgentConfig.user_id == user_id).order_by(UserAgentConfig.id)
        )
        return result.scalars().all()

    async def get(self, id: int) -> UserAgentConfig | None:
        result = await self.session.execute(select(UserAgentConfig).where(UserAgentConfig.id == id))
        return result.scalar_one_or_none()

    async def create(self, config: UserAgentConfig) -> UserAgentConfig:
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def update(self, config: UserAgentConfig) -> UserAgentConfig:
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def delete(self, id: int) -> bool:
        result = await self.session.execute(delete(UserAgentConfig).where(UserAgentConfig.id == id))
        await self.session.commit()
        return result.rowcount > 0

    async def get_active(self, user_id: int, provider: str) -> UserAgentConfig | None:
        result = await self.session.execute(
            select(UserAgentConfig).where(
                UserAgentConfig.user_id == user_id,
                UserAgentConfig.provider == provider,
                UserAgentConfig.is_active,
            )
        )
        return result.scalar_one_or_none()


class UserAgentPresetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(self, user_id: int) -> Sequence[UserAgentPreset]:
        result = await self.session.execute(
            select(UserAgentPreset).where(UserAgentPreset.user_id == user_id).order_by(UserAgentPreset.id)
        )
        return result.scalars().all()

    async def get(self, id: int) -> UserAgentPreset | None:
        result = await self.session.execute(select(UserAgentPreset).where(UserAgentPreset.id == id))
        return result.scalar_one_or_none()

    async def create(self, preset: UserAgentPreset) -> UserAgentPreset:
        self.session.add(preset)
        await self.session.commit()
        await self.session.refresh(preset)
        return preset

    async def update(self, preset: UserAgentPreset) -> UserAgentPreset:
        await self.session.commit()
        await self.session.refresh(preset)
        return preset

    async def delete(self, id: int) -> bool:
        result = await self.session.execute(delete(UserAgentPreset).where(UserAgentPreset.id == id))
        await self.session.commit()
        return result.rowcount > 0

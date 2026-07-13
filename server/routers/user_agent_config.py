"""用户智能体配置 API。

路由前缀: /api/v1/user-agent-config
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db import async_session_factory
from lib.db.models.user_agent_config import UserAgentConfig, UserAgentPreset
from lib.i18n import Translator
from server.auth import CurrentUser
from server.routers.custom_providers import ProviderConnectionRequest, _run_connection_test, _run_discover

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-agent-config", tags=["用户智能体配置"])


# ── Request/Response Models ─────────────────────────────────────────


class UserAgentConfigCreate(BaseModel):
    discovery_format: str
    display_name: str
    base_url: str
    api_key: str
    model: str | None = None
    embedding_model: str | None = None
    image_max_workers: int | None = None
    video_max_workers: int | None = None
    audio_max_workers: int | None = None
    price_unit: str | None = None
    price_input: float | None = None
    price_output: float | None = None
    currency: str | None = None
    is_active: bool = True
    extra_config: dict | None = None


class UserAgentConfigUpdate(BaseModel):
    discovery_format: str | None = None
    display_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    embedding_model: str | None = None
    image_max_workers: int | None = None
    video_max_workers: int | None = None
    audio_max_workers: int | None = None
    price_unit: str | None = None
    price_input: float | None = None
    price_output: float | None = None
    currency: str | None = None
    is_active: bool | None = None
    extra_config: dict | None = None


class UserAgentConfigResponse(BaseModel):
    id: int
    user_id: int
    discovery_format: str
    display_name: str
    base_url: str
    api_key_masked: str
    model: str | None = None
    embedding_model: str | None = None
    image_max_workers: int | None = None
    video_max_workers: int | None = None
    audio_max_workers: int | None = None
    price_unit: str | None = None
    price_input: float | None = None
    price_output: float | None = None
    currency: str | None = None
    is_active: bool
    extra_config: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None


class UserAgentPresetCreate(BaseModel):
    name: str
    provider: str
    model: str
    system_prompt: str | None = None
    config: dict | None = None


class UserAgentPresetUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    config: dict | None = None


class UserAgentPresetResponse(BaseModel):
    id: int
    user_id: int
    name: str
    provider: str
    model: str
    system_prompt: str | None = None
    config: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None


def mask_api_key(key: str) -> str:
    """脱敏 API Key"""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:4] + "***" + key[-4:]


def parse_extra_config(extra: str | None) -> dict | None:
    if not extra:
        return None
    try:
        return json.loads(extra)
    except Exception:
        return None


def config_to_response(config: UserAgentConfig) -> UserAgentConfigResponse:
    return UserAgentConfigResponse(
        id=config.id,
        user_id=config.user_id,
        discovery_format=config.discovery_format,
        display_name=config.display_name,
        base_url=config.base_url,
        api_key_masked=mask_api_key(config.api_key),
        model=config.model,
        embedding_model=config.embedding_model,
        image_max_workers=config.image_max_workers,
        video_max_workers=config.video_max_workers,
        audio_max_workers=config.audio_max_workers,
        price_unit=config.price_unit,
        price_input=config.price_input,
        price_output=config.price_output,
        currency=config.currency,
        is_active=config.is_active,
        extra_config=parse_extra_config(config.extra_config),
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


def preset_to_response(preset: UserAgentPreset) -> UserAgentPresetResponse:
    config_data = None
    if preset.config:
        try:
            config_data = json.loads(preset.config)
        except Exception:
            pass
    return UserAgentPresetResponse(
        id=preset.id,
        user_id=preset.user_id,
        name=preset.name,
        provider=preset.provider,
        model=preset.model,
        system_prompt=preset.system_prompt,
        config=config_data,
        created_at=preset.created_at.isoformat() if preset.created_at else None,
        updated_at=preset.updated_at.isoformat() if preset.updated_at else None,
    )


# ── Helper: Get user_id ─────────────────────────────────────────


async def get_user_id(user: CurrentUser) -> int | None:
    """从 CurrentUser 获取整数 user_id"""
    # 尝试直接转换
    try:
        return int(user.id)
    except (ValueError, TypeError):
        pass

    from lib.db.models.user import User

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.username == user.sub))
        user_row = result.scalar_one_or_none()
        return user_row.id if user_row else None


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


# ── Agent Config Endpoints ─────────────────────────────────────────


@router.get("/configs", response_model=list[UserAgentConfigResponse])
async def list_configs(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    for_user_id: int | None = None,
):
    """获取配置。管理员可通过 for_user_id 查询指定用户的配置。"""
    if for_user_id is None:
        uid = await get_user_id(user)
        if uid is None:
            return []
        target_user_id = uid
    else:
        target_user_id = for_user_id
    result = await session.execute(
        select(UserAgentConfig).where(UserAgentConfig.user_id == target_user_id).order_by(UserAgentConfig.id)
    )
    configs = result.scalars().all()
    return [config_to_response(c) for c in configs]


@router.get("/configs/{config_id}", response_model=UserAgentConfigResponse)
async def get_config(config_id: int, user: CurrentUser, session: AsyncSession = Depends(get_session)):
    """获取单个智能体配置"""
    user_id = await get_user_id(user)
    if user_id is None:
        raise HTTPException(status_code=404, detail="配置不存在")
    result = await session.execute(
        select(UserAgentConfig).where(
            UserAgentConfig.id == config_id,
            UserAgentConfig.user_id == user_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    return config_to_response(config)


@router.post("/configs/{config_id}/discover")
async def discover_models_by_config_id(
    config_id: int,
    user: CurrentUser,
    _t: Translator,
    session: AsyncSession = Depends(get_session),
):
    """使用已存储凭证发现指定配置的可用模型。"""
    result = await session.execute(select(UserAgentConfig).where(UserAgentConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    return await _run_discover(config.discovery_format, config.base_url, config.api_key, _t)


@router.get("/endpoints")
async def get_endpoint_catalog(user: CurrentUser):
    """获取 endpoint catalog（代理到 custom_providers）"""
    from server.routers.custom_providers import list_endpoint_catalog

    return await list_endpoint_catalog(user)


@router.post("/discover")
async def discover_models(
    body: ProviderConnectionRequest,
    user: CurrentUser,
    _t: Translator,
):
    """模型发现：根据 discovery_format + base_url + api_key 查询可用模型。"""
    return await _run_discover(body.discovery_format, body.base_url, body.api_key, _t)


@router.post("/test")
async def test_connection(
    body: ProviderConnectionRequest,
    user: CurrentUser,
    _t: Translator,
):
    """连接测试：验证 discovery_format + base_url + api_key 的连通性。"""
    from server.routers.custom_providers import _run_connection_test

    return await _run_connection_test(body.discovery_format, body.base_url, body.api_key, _t)


@router.post("/configs/{config_id}/test")
async def test_connection_by_config_id(
    config_id: int,
    user: CurrentUser,
    _t: Translator,
    session: AsyncSession = Depends(get_session),
):
    """使用已存储凭证测试指定配置的连通性。"""
    result = await session.execute(select(UserAgentConfig).where(UserAgentConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    return await _run_connection_test(config.discovery_format, config.base_url, config.api_key, _t)


@router.post("/configs", response_model=UserAgentConfigResponse)
async def create_config(
    data: UserAgentConfigCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    for_user_id: int | None = None,
):
    """创建智能体配置。管理员可通过 for_user_id 为指定用户创建配置。"""
    target_user_id = for_user_id if for_user_id is not None else await get_user_id(user)
    if target_user_id is None:
        raise HTTPException(status_code=400, detail="无法确定用户")

    config = UserAgentConfig(
        user_id=target_user_id,
        discovery_format=data.discovery_format,
        display_name=data.display_name,
        base_url=data.base_url,
        api_key=data.api_key,
        model=data.model,
        embedding_model=data.embedding_model,
        image_max_workers=data.image_max_workers,
        video_max_workers=data.video_max_workers,
        audio_max_workers=data.audio_max_workers,
        price_unit=data.price_unit,
        price_input=data.price_input,
        price_output=data.price_output,
        currency=data.currency,
        is_active=data.is_active,
        extra_config=json.dumps(data.extra_config) if data.extra_config else None,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config_to_response(config)


@router.put("/configs/{config_id}", response_model=UserAgentConfigResponse)
async def update_config(
    config_id: int,
    data: UserAgentConfigUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    for_user_id: int | None = None,
):
    """更新智能体配置。管理员可通过 for_user_id 更新指定用户的配置。"""
    if for_user_id is not None:
        target_user_id = for_user_id
    else:
        target_user_id = await get_user_id(user)
    if target_user_id is None:
        raise HTTPException(status_code=404, detail="配置不存在")

    result = await session.execute(
        select(UserAgentConfig).where(
            UserAgentConfig.id == config_id,
            UserAgentConfig.user_id == target_user_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    if data.discovery_format is not None:
        config.discovery_format = data.discovery_format
    if data.display_name is not None:
        config.display_name = data.display_name
    if data.base_url is not None:
        config.base_url = data.base_url
    if data.api_key is not None:
        config.api_key = data.api_key
    if data.model is not None:
        config.model = data.model
    if data.embedding_model is not None:
        config.embedding_model = data.embedding_model
    if data.image_max_workers is not None:
        config.image_max_workers = data.image_max_workers
    if data.video_max_workers is not None:
        config.video_max_workers = data.video_max_workers
    if data.audio_max_workers is not None:
        config.audio_max_workers = data.audio_max_workers
    if data.price_unit is not None:
        config.price_unit = data.price_unit
    if data.price_input is not None:
        config.price_input = data.price_input
    if data.price_output is not None:
        config.price_output = data.price_output
    if data.currency is not None:
        config.currency = data.currency
    if data.is_active is not None:
        config.is_active = data.is_active
    if data.extra_config is not None:
        config.extra_config = json.dumps(data.extra_config)

    await session.commit()
    await session.refresh(config)
    return config_to_response(config)


@router.delete("/configs/{config_id}")
async def delete_config(
    config_id: int,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    for_user_id: int | None = None,
):
    """删除智能体配置。管理员可通过 for_user_id 删除指定用户的配置。"""
    if for_user_id is not None:
        target_user_id = for_user_id
    else:
        target_user_id = await get_user_id(user)
    if target_user_id is None:
        raise HTTPException(status_code=404, detail="配置不存在")

    result = await session.execute(
        select(UserAgentConfig).where(
            UserAgentConfig.id == config_id,
            UserAgentConfig.user_id == target_user_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    await session.delete(config)
    await session.commit()
    return {"deleted": config_id}


# ── Agent Preset Endpoints ─────────────────────────────────────────


@router.get("/presets", response_model=list[UserAgentPresetResponse])
async def list_presets(user: CurrentUser, session: AsyncSession = Depends(get_session)):
    """获取当前用户的所有预设"""
    user_id = await get_user_id(user)
    if user_id is None:
        return []
    result = await session.execute(
        select(UserAgentPreset).where(UserAgentPreset.user_id == user_id).order_by(UserAgentPreset.id)
    )
    presets = result.scalars().all()
    return [preset_to_response(p) for p in presets]


@router.post("/presets", response_model=UserAgentPresetResponse)
async def create_preset(
    data: UserAgentPresetCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """创建预设"""
    user_id = await get_user_id(user)
    if user_id is None:
        raise HTTPException(status_code=400, detail="无法确定用户")

    preset = UserAgentPreset(
        user_id=user_id,
        name=data.name,
        provider=data.provider,
        model=data.model,
        system_prompt=data.system_prompt,
        config=json.dumps(data.config) if data.config else None,
    )
    session.add(preset)
    await session.commit()
    await session.refresh(preset)
    return preset_to_response(preset)


@router.put("/presets/{preset_id}", response_model=UserAgentPresetResponse)
async def update_preset(
    preset_id: int,
    data: UserAgentPresetUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """更新预设"""
    user_id = await get_user_id(user)
    if user_id is None:
        raise HTTPException(status_code=404, detail="预设不存在")

    result = await session.execute(
        select(UserAgentPreset).where(
            UserAgentPreset.id == preset_id,
            UserAgentPreset.user_id == user_id,
        )
    )
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    if data.name is not None:
        preset.name = data.name
    if data.provider is not None:
        preset.provider = data.provider
    if data.model is not None:
        preset.model = data.model
    if data.system_prompt is not None:
        preset.system_prompt = data.system_prompt
    if data.config is not None:
        preset.config = json.dumps(data.config)

    await session.commit()
    await session.refresh(preset)
    return preset_to_response(preset)


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: int, user: CurrentUser, session: AsyncSession = Depends(get_session)):
    """删除预设"""
    user_id = await get_user_id(user)
    if user_id is None:
        raise HTTPException(status_code=404, detail="预设不存在")

    result = await session.execute(
        select(UserAgentPreset).where(
            UserAgentPreset.id == preset_id,
            UserAgentPreset.user_id == user_id,
        )
    )
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    await session.delete(preset)
    await session.commit()
    return {"deleted": preset_id}

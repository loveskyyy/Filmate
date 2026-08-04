"""按 project > legacy > custom provider default > None 解析每次生成调用的分辨率。"""

from __future__ import annotations

# 当 resolve_resolution 返回 None 时下游的保底分辨率。Grok 即便 registry 声明 1080p
# 也可能被 xai_sdk 拒收，故按 provider 区分。
PROVIDER_FALLBACK_RESOLUTION: dict[str, str] = {
    "gemini": "1080p",
    "ark": "720p",
    "grok": "720p",
    "openai": "720p",
    # MiniMax 海螺缺省 768P：1080P 仅 6s，默认落 768P 避免与 10s 档冲突。
    "minimax": "768p",
    # filmate (sk.aistore777.top) 全部 resolution+seconds 组合仅 720P（从 API 错误信息
    # 看到：{resolution=720P, seconds=4}; ...；SD2.0 标准 优惠版 / GPT image2 1K 等
    # 所有 model 都是如此）。model_settings 里没显式设 resolution 的项目（参考生视频
    # reference_video 路径常见）就走这里 720P，否则 filmate API 返回 400 报
    # "参数组合不在支持范围内"。需要更精细 1080P 的 model 仍可在
    # model_settings[provider/model].resolution 显式覆盖。
    "filmate": "720p",
}


def get_provider_fallback(provider_id: str | None, default: str = "1080p") -> str:
    """对 registry ID（如 ``gemini-aistudio``）归一化到短前缀后查 fallback。"""
    if not provider_id:
        return default
    if provider_id in PROVIDER_FALLBACK_RESOLUTION:
        return PROVIDER_FALLBACK_RESOLUTION[provider_id]
    short = provider_id.split("-", 1)[0]
    return PROVIDER_FALLBACK_RESOLUTION.get(short, default)


def _from_project(project: dict, provider_id: str, model_id: str) -> str | None:
    # 内层也用 `or {}` 是因为 dict.get("k", {}) 在 value 显式为 None 时会返回 None，
    # 导致后续链调 AttributeError；project.json 手编可能出现这种脏值。
    key = f"{provider_id}/{model_id}"
    override = ((project.get("model_settings") or {}).get(key) or {}).get("resolution")
    if override:
        return override
    legacy = ((project.get("video_model_settings") or {}).get(model_id) or {}).get("resolution")
    if legacy:
        return legacy
    return None


async def get_custom_resolution_default(provider_id: str | None, model_id: str | None) -> str | None:
    """自定义供应商的模型默认 resolution（CustomProviderModel.resolution），其他一律 None。"""
    from lib.custom_provider import is_custom_provider

    if not provider_id or not model_id or not is_custom_provider(provider_id):
        return None
    from lib.custom_provider import parse_provider_id
    from lib.db import async_session_factory
    from lib.db.repositories.custom_provider_repo import CustomProviderRepository

    try:
        db_id = parse_provider_id(provider_id)
    except ValueError:
        return None

    async with async_session_factory() as session:
        repo = CustomProviderRepository(session)
        model = await repo.get_model_by_ids(db_id, model_id)
        return model.resolution if model else None


async def resolve_resolution(project: dict, provider_id: str, model_id: str) -> str | None:
    """按 project.model_settings → legacy video_model_settings → 自定义供应商默认 → None。

    None 代表“调用时不传 SDK resolution 参数”。
    """
    from_project = _from_project(project, provider_id, model_id)
    if from_project:
        return from_project
    return await get_custom_resolution_default(provider_id, model_id)

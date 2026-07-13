"""Custom provider model discovery (by discovery_format, returns endpoint)."""

from __future__ import annotations

import asyncio
import logging

from google import genai

from lib.config.anthropic_url import derive_anthropic_endpoints
from lib.custom_provider.endpoints import endpoint_to_media_type, infer_endpoint
from lib.httpx_shared import get_http_client

logger = logging.getLogger(__name__)


async def discover_models(
    *,
    discovery_format: str,
    base_url: str | None,
    api_key: str,
) -> list[dict]:
    """Query available models from provider, each item annotated with endpoint.

    Returns:
        list of dict: model_id, display_name, endpoint, is_default, is_enabled
    """
    if discovery_format == "openai":
        return await _discover_openai(base_url, api_key)
    elif discovery_format == "google":
        return await _discover_google(base_url, api_key)
    elif discovery_format == "anthropic":
        return await _discover_anthropic(base_url, api_key)
    else:
        raise ValueError(
            f"Unsupported discovery_format: {discovery_format!r}, supported: 'openai', 'google', 'anthropic'"
        )


async def _discover_openai(base_url: str | None, api_key: str) -> list[dict]:
    from httpx import Client

    def _sync():
        from lib.config.url_utils import ensure_openai_base_url

        effective_url = ensure_openai_base_url(base_url)
        if not effective_url.endswith("/v1"):
            effective_url = effective_url.rstrip("/") + "/v1"
        models_url = effective_url + "/models"

        with Client(timeout=30.0) as http_client:
            response = http_client.get(models_url, headers={"Authorization": f"Bearer {api_key}"})
            if response.status_code != 200:
                raise Exception(f"API error status {response.status_code}: {response.text[:200]}")
            data = response.json()

        logger.info("API response type: %s", type(data).__name__)

        # Parse models list
        raw_models = data.get("data", [])
        if not isinstance(raw_models, list):
            if isinstance(raw_models, dict):
                raw_models = raw_models.get("data", [])
            else:
                raw_models = []

        logger.info("Found %d models", len(raw_models))

        result = []
        for item in raw_models:
            model_id = item.get("id") or item.get("model_id") or item.get("model") or item.get("name")
            if not model_id:
                continue
            model_id = str(model_id)
            display_name = str(item.get("display_name") or item.get("name") or item.get("model") or model_id)

            # Determine endpoint
            # 1. Custom API format: has type_name field (视频/图片/对话/其他)
            type_name = str(item.get("type_name") or "")
            # model_type = item.get("type")  # available for future use

            if type_name:
                # Custom API format with type_name
                if "视频" in type_name:
                    endpoint = "openai-video"
                elif "图片" in type_name:
                    endpoint = "openai-images"
                elif "语音" in type_name or "音频" in type_name:
                    endpoint = "openai-tts"
                elif "对话" in type_name or "文本" in type_name:
                    endpoint = "openai-chat"
                else:
                    endpoint = "openai-chat"
            else:
                # 2. Standard OpenAI format: supported_endpoint_types
                supported = [str(x).lower() for x in item.get("supported_endpoint_types") or []]
                owned_by = str(item.get("owned_by") or "")

                if "openai-video" in supported:
                    endpoint = "openai-video"
                elif "image-generation" in supported:
                    endpoint = "openai-images"
                elif "google" in owned_by.lower():
                    endpoint = "gemini-generate"
                # 3. Fallback: infer from model_id keywords
                elif any(
                    k in model_id.lower()
                    for k in [
                        "-i2v",
                        "-t2v",
                        "-v2v",
                        "video",
                        "kling",
                        "hailuo",
                        "sora",
                        "wan2",
                        "runway",
                        "pika",
                        "vidu",
                        "seedance",
                        "hunyuan",
                    ]
                ):
                    endpoint = "openai-video"
                elif any(k in model_id.lower() for k in ["image", "dall", "banana", "seedream"]):
                    endpoint = "openai-images"
                else:
                    endpoint = "openai-chat"

            result.append(
                {
                    "id": model_id,
                    "display_name": display_name,
                    "endpoint": endpoint,
                    "is_default": False,
                    "is_enabled": True,
                }
            )

        return result

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.error("_discover_openai error: %s", e)
        raise


async def _discover_google(base_url: str | None, api_key: str) -> list[dict]:
    def _sync():
        from lib.config.url_utils import ensure_google_base_url

        kwargs: dict = {"api_key": api_key}
        effective_url = ensure_google_base_url(base_url) if base_url else None
        if effective_url:
            kwargs["http_options"] = {"base_url": effective_url}
        client = genai.Client(**kwargs)
        raw_models = client.models.list()

        entries: list[tuple[str, str]] = []
        for m in raw_models:
            if not m.name:
                continue
            model_id: str = m.name
            if model_id.startswith("models/"):
                model_id = model_id[len("models/") :]
            entries.append((model_id, infer_endpoint(model_id, "google")))

        entries.sort(key=lambda e: e[0])
        return _build_result_list(entries)

    return await asyncio.to_thread(_sync)


async def _discover_anthropic(base_url: str | None, api_key: str) -> list[dict]:
    """Anthropic Messages API GET /v1/models discovery.
    Returns dict in same format as OpenAI/Google, but endpoint is empty string
    (anthropic does not participate in ENDPOINT_REGISTRY dispatch, frontend only reads model_id).
    """
    ep = derive_anthropic_endpoints(base_url or "https://api.anthropic.com")
    normalized = ep.discovery_root or "https://api.anthropic.com"
    resp = await get_http_client().get(
        f"{normalized}/v1/models",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    entries = sorted(
        (m for m in data.get("data", []) if m.get("id")),
        key=lambda m: m["id"],
    )
    return [
        {
            "model_id": m["id"],
            "display_name": m.get("display_name") or m["id"],
            "endpoint": "",
            "is_default": False,
            "is_enabled": True,
        }
        for m in entries
    ]


def _build_result_list(entries: list[tuple[str, str]]) -> list[dict]:
    """Each media_type takes first item as default."""
    seen_media: set[str] = set()
    result: list[dict] = []
    for model_id, endpoint in entries:
        try:
            media = endpoint_to_media_type(endpoint)
        except Exception as e:
            logger.warning("Failed to get media_type for endpoint %s: %s, skip", endpoint, e)
            continue
        is_default = media not in seen_media
        seen_media.add(media)
        result.append(
            {
                "model_id": model_id,
                "display_name": model_id,
                "endpoint": endpoint,
                "is_default": is_default,
                "is_enabled": True,
            }
        )
    return result

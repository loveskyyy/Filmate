"""FilmateImageBackend — Filmate 图片生成后端。

基于 OpenAI 兼容 Images API。
"""

from __future__ import annotations

import logging
from pathlib import Path

from lib.image_backends.base import (
    ImageBackend,
    ImageCapability,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from lib.logging_utils import format_kwargs_for_log
from lib.retry import with_retry_async

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://sk.aistore777.top/api/v1"
DEFAULT_MODEL = "GPT image2"


def _map_resolution(resolution: str | None) -> str | None:
    """映射分辨率字符串。"""
    if resolution is None:
        return None
    return resolution


def _map_aspect_ratio(aspect_ratio: str) -> str:
    """映射宽高比字符串。"""
    return aspect_ratio


class FilmateImageBackend(ImageBackend):
    """Filmate 图片生成后端，使用 OpenAI SDK。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        from openai import AsyncOpenAI

        self._api_key = api_key or ""
        self._base_url = base_url or DEFAULT_BASE_URL
        self._model = model or DEFAULT_MODEL
        self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url, timeout=120.0)
        self._capabilities: set[ImageCapability] = {
            ImageCapability.TEXT_TO_IMAGE,
            ImageCapability.IMAGE_TO_IMAGE,
        }

    @property
    def name(self) -> str:
        return "filmate"

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[ImageCapability]:
        return self._capabilities

    @with_retry_async(max_attempts=3, backoff_seconds=(2, 4, 8))
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """生成图片，使用 OpenAI Images API。"""
        has_refs = bool(request.reference_images)

        if not self._api_key:
            logger.error("Filmate API Key 为空！")

        # 构建请求参数
        kwargs: dict = {
            "model": self._model,
            "prompt": request.prompt,
        }

        # 处理尺寸参数
        aspect_ratio = request.aspect_ratio or "1:1"
        kwargs["size"] = _map_aspect_ratio(aspect_ratio)

        # 处理参考图 (I2I)
        if has_refs:
            ref_urls = [ref.path for ref in request.reference_images]
            kwargs["image"] = ref_urls[0] if len(ref_urls) == 1 else ref_urls

        logger.info(
            "提交 Filmate 图片生成任务 kwargs=%s",
            format_kwargs_for_log({"model": kwargs.get("model"), "prompt_len": len(kwargs.get("prompt", ""))}),
        )

        response = await self._client.images.generate(**kwargs)

        logger.info("Filmate 图片生成响应: %s", response)

        # 获取图片 URL
        if not response.data:
            raise RuntimeError(f"Filmate 图片生成返回空数据: {response}")

        image_data = response.data[0]
        image_url = image_data.url or image_data.b64_json
        if not image_url:
            raise RuntimeError(f"Filmate 图片生成返回空 URL: {response}")

        # 下载图片
        output_path = await self._download_image(image_url)

        return ImageGenerationResult(
            url=image_url,
            output_path=output_path,
            provider=self.name,
            model=self.model,
        )

    async def _download_image(self, url: str) -> Path:
        """下载图片到临时文件。"""
        import tempfile
        from pathlib import Path

        response = await self._client._client.get(url)
        response.raise_for_status()

        content = response.content

        # 确定文件扩展名
        ext = "png"
        if url.endswith(".jpg") or url.endswith(".jpeg"):
            ext = "jpg"
        elif url.endswith(".webp"):
            ext = "webp"

        # 保存到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as f:
            f.write(content)
            return Path(f.name)

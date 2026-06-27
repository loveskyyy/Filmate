"""FilmateImageBackend — Filmate 图片生成后端。

基于 OpenAI 兼容 API，使用任务轮询模式获取结果。
"""

from __future__ import annotations

import asyncio
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

# 任务状态码
_TASK_STATUS_PENDING = 0
_TASK_STATUS_SUCCESS = 1
_TASK_STATUS_FAILED = 2
_TASK_STATUS_PROCESSING = 3
_TASK_STATUS_SUBMITTED = 4

# 重试配置
_POLL_INTERVAL = 2.0  # 秒
_MAX_POLL_ATTEMPTS = 60  # 最多等待 120 秒


class FilmateImageBackend(ImageBackend):
    """Filmate 图片生成后端，使用任务轮询模式。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        import httpx

        self._api_key = api_key or ""
        self._base_url = base_url or DEFAULT_BASE_URL
        self._model = model or DEFAULT_MODEL
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
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
        """生成图片，使用任务提交 + 轮询模式。"""
        has_refs = bool(request.reference_images)

        # 构建请求头
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # 构建请求体
        payload: dict = {
            "model": self._model,
            "prompt": request.prompt,
        }

        # 处理尺寸参数
        aspect_ratio = request.aspect_ratio or "1:1"
        payload["size"] = aspect_ratio

        # 处理参考图 (I2I)
        if has_refs:
            ref_urls = [ref.path for ref in request.reference_images]
            if len(ref_urls) == 1:
                payload["image"] = ref_urls[0]
            else:
                payload["images"] = ref_urls

        logger.info(
            "提交 Filmate 图片生成任务 kwargs=%s, base_url=%s, api_key=%s",
            format_kwargs_for_log({"model": payload.get("model"), "prompt_len": len(payload.get("prompt", ""))}),
            self._base_url,
            self._api_key[:8] + "..." if self._api_key else "None",
        )

        # 提交任务
        submit_url = f"{self._base_url}/images/generations"
        response = await self._client.post(submit_url, json=payload, headers=headers)
        response.raise_for_status()

        result = response.json()
        logger.info("Filmate 图片提交响应: %s", result)

        if result.get("code") != 200:
            raise RuntimeError(f"Filmate 图片提交失败: {result}")

        task_data = result.get("data", {})
        task_id = task_data.get("task_id")
        if not task_id:
            raise RuntimeError(f"Filmate 响应缺少 task_id: {result}")

        logger.info("Filmate 图片任务已提交: task_id=%s", task_id)

        # 轮询获取结果
        image_url = await self._poll_task_result(task_id, headers)

        # 下载图片
        output_path = await self._download_image(image_url)

        return ImageGenerationResult(
            url=image_url,
            output_path=output_path,
            provider=self.name,
            model=self.model,
        )

    @with_retry_async(max_attempts=3, backoff_seconds=(2, 4, 8))
    async def _poll_task_result(self, task_id: str, headers: dict) -> str:
        """轮询任务结果直到完成。"""
        poll_url = f"{self._base_url}/tasks/{task_id}"

        for attempt in range(_MAX_POLL_ATTEMPTS):
            await asyncio.sleep(_POLL_INTERVAL)

            response = await self._client.get(poll_url, headers=headers)
            response.raise_for_status()

            result = response.json()
            if result.get("code") != 200:
                logger.warning("轮询任务状态失败: %s", result)
                continue

            task_data = result.get("data", {})
            status = task_data.get("status")

            if status == _TASK_STATUS_SUCCESS:
                image_url = task_data.get("image_url") or task_data.get("url")
                if not image_url:
                    raise RuntimeError(f"Filmate 任务成功但无图片 URL: {task_data}")
                logger.info("Filmate 图片任务完成: task_id=%s, url=%s", task_id, image_url)
                return image_url

            elif status == _TASK_STATUS_FAILED:
                error_msg = task_data.get("error", "未知错误")
                raise RuntimeError(f"Filmate 图片生成失败: {error_msg}")

            elif status in (_TASK_STATUS_PENDING, _TASK_STATUS_PROCESSING, _TASK_STATUS_SUBMITTED):
                logger.debug("轮询 Filmate 图片任务: task_id=%s status=%s attempt=%d", task_id, status, attempt)
                continue

            else:
                logger.warning("未知任务状态: status=%s task_data=%s", status, task_data)

        raise TimeoutError(f"Filmate 图片任务轮询超时: task_id={task_id}")

    async def _download_image(self, url: str) -> Path:
        """下载图片到临时文件。"""
        import tempfile

        response = await self._client.get(url)
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

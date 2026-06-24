"""RunningHub 图片生成后端。

基于 RunningHub 标准模型 API:
- POST /openapi/v2/{model}/text-to-image (文生图)
- POST /openapi/v2/{model}/image-to-image (图生图，直接使用已有图片URL或base64)
- POST /openapi/v2/query (任务查询)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from lib.image_backends.base import (
    ImageCapability,
    ImageCapabilityError,
    ImageGenerationRequest,
    ImageGenerationResult,
    image_to_base64_data_uri,
)
from lib.providers import PROVIDER_RUNNINGHUB
from lib.retry import BASE_RETRYABLE_ERRORS, with_retry_async

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.runninghub.cn/openapi/v2"
DEFAULT_MODEL = "rhart-image-g-2-official"
_POLL_INTERVAL_SECONDS = 3.0
_MAX_POLL_TIMEOUT_SECONDS = 300.0

_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    TimeoutError,
    httpx.TimeoutException,
    httpx.HTTPStatusError,
    *BASE_RETRYABLE_ERRORS,
)


class RunningHubImageBackend:
    """RunningHub 图片生成后端。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or ""
        self._base_url = base_url or _BASE_URL
        self._model = model or DEFAULT_MODEL
        self._capabilities: set[ImageCapability] = {
            ImageCapability.TEXT_TO_IMAGE,
            ImageCapability.IMAGE_TO_IMAGE,
        }

    @property
    def name(self) -> str:
        return PROVIDER_RUNNINGHUB

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[ImageCapability]:
        return self._capabilities

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        has_refs = bool(request.reference_images)
        if has_refs and ImageCapability.IMAGE_TO_IMAGE not in self._capabilities:
            raise ImageCapabilityError("image_endpoint_mismatch_no_i2i", model=self._model)
        if not has_refs and ImageCapability.TEXT_TO_IMAGE not in self._capabilities:
            raise ImageCapabilityError("image_endpoint_mismatch_no_t2i", model=self._model)
        return await (self._generate_i2i(request) if has_refs else self._generate_t2i(request))

    @with_retry_async(retryable_errors=_RETRYABLE_ERRORS)
    async def _generate_t2i(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        payload = {
            "prompt": request.prompt,
            "aspectRatio": request.aspect_ratio,
            "resolution": request.image_size or "2k",
            "quality": "medium",
        }
        logger.info(
            "RunningHub 文生图开始: model=%s, kwargs=%s",
            self._model,
            {
                "prompt": request.prompt[:100],
                "aspectRatio": payload["aspectRatio"],
                "resolution": payload["resolution"],
            },
        )

        task_id = await self._submit_task("text-to-image", payload)
        return await self._poll_and_download(task_id, request)

    @with_retry_async(retryable_errors=_RETRYABLE_ERRORS)
    async def _generate_i2i(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        image_urls = []
        for ref in request.reference_images:
            url = self._resolve_image_url(Path(ref.path))
            image_urls.append(url)

        payload = {
            "prompt": request.prompt,
            "imageUrls": image_urls,
            "aspectRatio": request.aspect_ratio,
            "resolution": request.image_size or "1k",
            "quality": "medium",
        }
        logger.info(
            "RunningHub 图生图开始: model=%s, kwargs=%s",
            self._model,
            {
                "prompt": request.prompt[:100] if request.prompt else None,
                "imageCount": len(image_urls),
                "aspectRatio": payload["aspectRatio"],
            },
        )

        task_id = await self._submit_task("image-to-image", payload)
        return await self._poll_and_download(task_id, request)

    def _resolve_image_url(self, path: Path) -> str:
        if path.exists():
            return image_to_base64_data_uri(path)
        return str(path)

    @with_retry_async(retryable_errors=_RETRYABLE_ERRORS)
    async def _submit_task(self, endpoint: str, payload: dict) -> str:
        url = f"{self._base_url}/{self._model}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("taskId")
        if not task_id:
            raise RuntimeError(f"RunningHub 提交任务失败: {data}")
        logger.info("RunningHub 任务提交成功: taskId=%s", task_id)
        return task_id

    async def _poll_and_download(self, task_id: str, request: ImageGenerationRequest) -> ImageGenerationResult:
        start = asyncio.get_event_loop().time()

        while True:
            status = await self._check_task_status(task_id)

            if status.get("status") == "SUCCESS":
                results = status.get("results") or []
                for result in results:
                    if result.get("url"):
                        await self._download_image(result["url"], request.output_path)
                        logger.info("RunningHub 图片生成完成: %s", request.output_path)
                        return ImageGenerationResult(
                            image_path=request.output_path,
                            provider=PROVIDER_RUNNINGHUB,
                            model=self._model,
                            image_uri=result["url"],
                        )
                raise RuntimeError(f"RunningHub 任务成功但无图片URL: {status}")

            if status.get("status") == "FAILED":
                error_msg = status.get("errorMessage") or status.get("error", {}).get("message") or "unknown error"
                raise RuntimeError(f"RunningHub 图片生成失败: {error_msg}")

            elapsed = asyncio.get_event_loop().time() - start
            if elapsed >= _MAX_POLL_TIMEOUT_SECONDS:
                raise TimeoutError(f"RunningHub 任务超时 ({_MAX_POLL_TIMEOUT_SECONDS}秒)")

            logger.info(
                "RunningHub 图片生成中... taskId=%s, status=%s, elapsed=%ds",
                task_id,
                status.get("status"),
                int(elapsed),
            )
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    @with_retry_async(retryable_errors=_RETRYABLE_ERRORS)
    async def _check_task_status(self, task_id: str) -> dict:
        url = f"{self._base_url}/query"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = {"taskId": task_id}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    @with_retry_async(retryable_errors=_RETRYABLE_ERRORS)
    async def _download_image(self, url: str, output_path: Path) -> None:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        def _save():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(resp.content)

        await asyncio.to_thread(_save)

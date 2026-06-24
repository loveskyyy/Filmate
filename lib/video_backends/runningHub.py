"""RunningHub 视频生成后端。

基于 RunningHub 标准模型 API:
- POST /openapi/v2/{model}/text-to-video (文生视频)
- POST /openapi/v2/{model}/image-to-video (图生视频，支持首尾帧)
- POST /openapi/v2/{model}/multimodal-video (多模态生视频)
- POST /openapi/v2/query (任务查询)
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

import httpx

from lib.providers import PROVIDER_RUNNINGHUB
from lib.retry import BASE_RETRYABLE_ERRORS, with_retry_async
from lib.video_backends.base import (
    VideoCapabilities,
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
    poll_with_retry,
)

logger = logging.getLogger(__name__)

IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _local_image_to_base64_data_uri(image_path: Path) -> str:
    """将本地图片转为 base64 data URI。"""
    suffix = image_path.suffix.lower()
    mime_type = IMAGE_MIME_TYPES.get(suffix, "image/png")
    image_data = image_path.read_bytes()
    b64 = base64.b64encode(image_data).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


_BASE_URL = "https://www.runninghub.cn/openapi/v2"
_DEFAULT_MODEL = "rhart-video/sparkvideo-2.0"
MODEL_T2V = "rhart-video/sparkvideo-2.0-fast"
MODEL_I2V = "rhart-video/sparkvideo-2.0"
MODEL_MULTIMODAL = "rhart-video/sparkvideo-2.0"

_POLL_INTERVAL_SECONDS = 5.0
_MIN_POLL_TIMEOUT_SECONDS = 1800.0  # 30分钟
_POLL_TIMEOUT_PER_SECOND = 120.0

_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    TimeoutError,
    httpx.TimeoutException,
    httpx.HTTPStatusError,
    *BASE_RETRYABLE_ERRORS,
)


class RunningHubVideoBackend:
    """RunningHub 视频生成后端。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or ""
        self._base_url = base_url or _BASE_URL
        self._model = model or _DEFAULT_MODEL
        self._capabilities: set[VideoCapability] = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
            VideoCapability.GENERATE_AUDIO,
            VideoCapability.SEED_CONTROL,
        }

    @property
    def name(self) -> str:
        return PROVIDER_RUNNINGHUB

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._capabilities

    @property
    def video_capabilities(self) -> VideoCapabilities:
        return VideoCapabilities(
            first_frame=True,
            last_frame=True,
            reference_images=True,
            max_reference_images=5,
        )

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        has_refs = bool(request.reference_images)
        has_start_image = request.start_image and Path(request.start_image).exists()

        if has_refs:
            return await self._generate_multimodal(request)
        if has_start_image:
            return await self._generate_i2v_with_frames(request)
        return await self._generate_t2v(request)

    async def _generate_t2v(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        payload = {
            "prompt": request.prompt,
            "resolution": self._resolve_resolution(request.resolution),
            "duration": str(request.duration_seconds),
            "generateAudio": request.generate_audio,
            "ratio": self._map_aspect_ratio(request.aspect_ratio),
            "webSearch": False,
            "returnLastFrame": False,
            "seed": request.seed if request.seed is not None else -1,
        }

        logger.info("RunningHub 文生视频开始: model=%s, duration=%ss", MODEL_T2V, payload["duration"])
        logger.info(
            "调用 RunningHub 视频 API (T2V): %s",
            {"prompt": payload["prompt"][:100], "resolution": payload["resolution"]},
        )

        task_id = await self._submit_task(f"{MODEL_T2V}/text-to-video", payload)
        return await self._poll_and_download(task_id, request)

    async def _generate_i2v_with_frames(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        first_frame_url = self._resolve_image_url(request.start_image) if request.start_image else None
        last_frame_url = None
        if request.end_image and Path(request.end_image).exists():
            last_frame_url = self._resolve_image_url(request.end_image)

        payload = {
            "prompt": request.prompt,
            "resolution": self._resolve_resolution(request.resolution),
            "duration": str(request.duration_seconds),
            "firstFrameUrl": first_frame_url,
            "lastFrameUrl": last_frame_url,
            "generateAudio": request.generate_audio,
            "ratio": self._map_aspect_ratio(request.aspect_ratio),
            "realPersonMode": True,
            "seed": request.seed if request.seed is not None else -1,
        }

        logger.info("RunningHub 图生视频(首尾帧)开始: model=%s, duration=%ss", MODEL_I2V, payload["duration"])

        task_id = await self._submit_task(f"{MODEL_I2V}/image-to-video", payload)
        return await self._poll_and_download(task_id, request)

    async def _generate_multimodal(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        image_urls = []
        if request.reference_images:
            for ref in request.reference_images:
                url = self._resolve_image_url(ref)
                image_urls.append(url)

        prompt_text = request.prompt or ""
        if not prompt_text and image_urls:
            prompt_text = "Generate video from reference images"

        payload = {
            "prompt": prompt_text,
            "resolution": self._resolve_resolution(request.resolution),
            "duration": str(request.duration_seconds),
            "imageUrls": image_urls,
            "generateAudio": request.generate_audio,
            "ratio": self._map_aspect_ratio(request.aspect_ratio),
            "realPersonMode": True,
            "seed": request.seed if request.seed is not None else -1,
        }

        logger.info("RunningHub 多模态生视频开始: imageCount=%d, duration=%ss", len(image_urls), payload["duration"])

        task_id = await self._submit_task(f"{MODEL_MULTIMODAL}/multimodal-video", payload)
        return await self._poll_and_download(task_id, request)

    def _resolve_image_url(self, path: Path | str | None) -> str | None:
        if path is None:
            return None
        p = Path(path) if not isinstance(path, Path) else path
        if p.exists():
            return _local_image_to_base64_data_uri(p)
        return str(p)

    def _resolve_resolution(self, resolution: str | None) -> str:
        if resolution:
            return resolution
        return "720p"

    def _map_aspect_ratio(self, aspect_ratio: str) -> str:
        mapping = {
            "9:16": "9:16",
            "16:9": "16:9",
            "1:1": "1:1",
            "4:3": "4:3",
        }
        return mapping.get(aspect_ratio, "adaptive")

    @with_retry_async(retryable_errors=_RETRYABLE_ERRORS)
    async def _submit_task(self, endpoint: str, payload: dict) -> str:
        url = f"{self._base_url}/{endpoint}"
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
            raise RuntimeError(f"RunningHub 提交视频任务失败: {data}")
        logger.info("RunningHub 视频任务提交成功: taskId=%s", task_id)
        return task_id

    async def _poll_and_download(self, task_id: str, request: VideoGenerationRequest) -> VideoGenerationResult:
        max_wait = max(_MIN_POLL_TIMEOUT_SECONDS, float(request.duration_seconds) * _POLL_TIMEOUT_PER_SECOND)

        status = await poll_with_retry(
            poll_fn=lambda: self._check_task_status(task_id),
            is_done=lambda s: s.get("status") == "SUCCESS",
            is_failed=lambda s: s.get("errorMessage") if s.get("status") == "FAILED" else None,
            poll_interval=_POLL_INTERVAL_SECONDS,
            max_wait=max_wait,
            retryable_errors=_RETRYABLE_ERRORS,
            label="RunningHub",
            on_progress=lambda s, elapsed: logger.info(
                "RunningHub 视频生成中... taskId=%s, status=%s, elapsed=%ds",
                task_id,
                s.get("status"),
                int(elapsed),
            ),
        )

        results = status.get("results") or []
        video_url = None
        for result in results:
            if result.get("url"):
                video_url = result["url"]
                break

        if not video_url:
            raise RuntimeError(f"RunningHub 任务完成但无视频URL: {status}")

        await self._download_video(video_url, request.output_path)
        logger.info("RunningHub 视频下载完成: %s", request.output_path)

        return VideoGenerationResult(
            video_path=request.output_path,
            provider=PROVIDER_RUNNINGHUB,
            model=self._model,
            duration_seconds=request.duration_seconds,
            video_uri=video_url,
            task_id=task_id,
            generate_audio=request.generate_audio,
        )

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

    async def _download_video(self, url: str, output_path: Path) -> None:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("GET", url, timeout=120.0) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                resp.raise_for_status()
                chunks = []
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    chunks.append(chunk)

        def _write():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)

        await asyncio.to_thread(_write)

    async def resume_video(self, job_id: str, request: VideoGenerationRequest) -> VideoGenerationResult:
        raise NotImplementedError("RunningHub 暂不支持任务接续")

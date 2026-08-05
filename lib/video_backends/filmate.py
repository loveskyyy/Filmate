"""FilmateVideoBackend — Filmate 视频生成后端。

基于 OpenAI 兼容 API，使用任务轮询模式获取结果。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from lib.logging_utils import format_kwargs_for_log
from lib.providers import PROVIDER_FILMATE
from lib.retry import DOWNLOAD_BACKOFF_SECONDS, DOWNLOAD_MAX_ATTEMPTS, with_retry_async
from lib.video_backends.base import (
    VideoBackend,
    VideoCapabilities,
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
    download_video,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://sk.aistore777.top/api/v1"
DEFAULT_MODEL = "Seedance 2.0 标准"

# 任务状态码
_TASK_STATUS_PENDING = 0
_TASK_STATUS_SUCCESS = 1
_TASK_STATUS_FAILED = 2
_TASK_STATUS_PROCESSING = 3
_TASK_STATUS_SUBMITTED = 4

# 轮询配置
_POLL_INTERVAL = 3.0  # 秒
_MAX_POLL_ATTEMPTS = 120  # 最多等待 360 秒（6分钟）

# Happy Horse 模型支持首尾帧
_HAPPY_HORSE_MODEL = "Happy Horse"


def _is_video_model(model: str) -> bool:
    """检查是否为视频模型。"""
    video_keywords = ["Seedance", "Happy Horse", "SD2", "video"]
    return any(kw.lower() in model.lower() for kw in video_keywords)


class FilmateVideoBackend(VideoBackend):
    """Filmate 视频生成后端，使用任务轮询模式。"""

    # Happy Horse 支持首尾帧（通过 VideoCapabilities.last_frame 配置）
    _MODEL_CAPABILITIES: dict[str, set[VideoCapability]] = {
        "Happy Horse": {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
        },
    }

    _DEFAULT_CAPABILITIES: set[VideoCapability] = {
        VideoCapability.TEXT_TO_VIDEO,
        VideoCapability.IMAGE_TO_VIDEO,
        VideoCapability.SEED_CONTROL,
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        files_base_url: str | None = None,
    ):
        import os

        import httpx

        self._api_key = api_key or ""
        # 规范化 base_url，确保包含 /api/v1 路径
        self._base_url = self._normalize_base_url(base_url) or DEFAULT_BASE_URL
        self._model = model or DEFAULT_MODEL
        # 文件服务基础 URL，用于构建可访问的参考图 URL
        # 支持环境变量 FILMATE_FILES_BASE_URL 或直接传入
        self._files_base_url = files_base_url or os.environ.get("FILMATE_FILES_BASE_URL") or None
        # 下载超时设置为 300 秒，视频文件较大可能需要更长时间
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0))
        self._capabilities = self._MODEL_CAPABILITIES.get(self._model, self._DEFAULT_CAPABILITIES)

    @property
    def name(self) -> str:
        return PROVIDER_FILMATE

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._capabilities

    @property
    def video_capabilities(self) -> VideoCapabilities:
        if self._model == _HAPPY_HORSE_MODEL:
            return VideoCapabilities(last_frame=True, reference_images=True, max_reference_images=4)
        return VideoCapabilities(reference_images=True, max_reference_images=4)

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """生成视频，使用任务提交 + 轮询模式。"""
        # 构建请求头
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # 构建请求体
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": request.prompt,
        }

        # 注意：Filmate API 只支持 resolution+seconds 组合，不支持 size
        # 错误信息显示支持的组合如 {resolution=720P, seconds=4}

        # 处理时长 - 必须在 resolution 之前处理，因为 API 验证组合
        if request.duration_seconds:
            payload["seconds"] = request.duration_seconds

        # 处理分辨率 - Filmate API 只认这个参数
        # 默认使用 720P（API 只支持 720P）
        resolution = request.resolution or "720P"
        resolution_map = {
            "480p": "480P",
            "720p": "720P",
            "1080p": "1080P",
        }
        payload["resolution"] = resolution_map.get(resolution.lower(), "720P")

        # 处理种子
        if request.seed is not None:
            # Filmate API 可能支持 seed，但根据文档没有明确
            pass

        # 处理参考图
        if request.reference_images:
            ref_urls = []
            for ref_path in request.reference_images:
                p = Path(ref_path) if not isinstance(ref_path, Path) else ref_path
                if p.exists():
                    # 尝试构建可访问的 URL
                    url = self._build_files_url(p, request.project_name)
                    if url:
                        ref_urls.append(url)
                    else:
                        # 无法构建 URL，记录警告但仍使用文件路径
                        logger.warning(
                            "无法为本地文件构建可访问 URL: %s，Filmate 可能无法访问",
                            str(ref_path),
                        )
                        ref_urls.append(str(ref_path))
                elif str(ref_path).startswith("http"):
                    ref_urls.append(str(ref_path))

            if len(ref_urls) == 1:
                payload["reference_image"] = ref_urls[0]
            elif len(ref_urls) > 1:
                payload["reference_images"] = ref_urls

        # 处理首尾帧（仅 Happy Horse 模型支持）
        if self._model == _HAPPY_HORSE_MODEL:
            if request.start_image:
                start_path = (
                    Path(request.start_image) if not isinstance(request.start_image, Path) else request.start_image
                )
                if start_path.exists():
                    payload["frame_start"] = str(start_path)
                elif str(start_path).startswith("http"):
                    payload["frame_start"] = str(start_path)

            if request.end_image:
                end_path = Path(request.end_image) if not isinstance(request.end_image, Path) else request.end_image
                if end_path.exists():
                    payload["frame_end"] = str(end_path)
                elif str(end_path).startswith("http"):
                    payload["frame_end"] = str(end_path)

        logger.info(
            "提交 Filmate 视频生成任务 kwargs=%s",
            format_kwargs_for_log(payload),
        )

        # 提交任务
        submit_url = f"{self._base_url}/video/generations"
        response = await self._client.post(submit_url, json=payload, headers=headers)
        response.raise_for_status()

        result = response.json()
        if result.get("code") != 200:
            raise RuntimeError(f"Filmate 视频提交失败: {result}")

        task_data = result.get("data", {})
        task_id = task_data.get("task_id")
        if not task_id:
            raise RuntimeError(f"Filmate 响应缺少 task_id: {result}")

        logger.info("Filmate 视频任务已提交: task_id=%s", task_id)

        # 轮询获取结果
        video_url = await self._poll_task_result(task_id, headers)

        # 下载视频
        output_path = request.output_path or Path(f"video_{task_id}.mp4")
        await self._download_video_with_retry(video_url, output_path)

        return VideoGenerationResult(
            video_path=output_path,
            provider=self.name,
            model=self.model,
            duration_seconds=request.duration_seconds or 5,
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
                video_url = task_data.get("result")
                if not video_url:
                    raise RuntimeError(f"Filmate 任务成功但无 result: {task_data}")
                # 解析 JSON 数组字符串（如果 API 返回的是 ["url"] 格式）
                video_url = self._parse_result_url(video_url)
                # 确保 video_url 是完整的 HTTP URL
                video_url = self._ensure_full_url(video_url)
                logger.info("Filmate 视频任务完成: task_id=%s video_url=%s", task_id, video_url)
                return video_url

            elif status == _TASK_STATUS_FAILED:
                error_msg = task_data.get("error", "未知错误")
                raise RuntimeError(f"Filmate 视频生成失败: {error_msg}")

            elif status in (_TASK_STATUS_PENDING, _TASK_STATUS_PROCESSING, _TASK_STATUS_SUBMITTED):
                logger.debug("轮询 Filmate 视频任务: task_id=%s status=%s attempt=%d", task_id, status, attempt)
                continue

            else:
                logger.warning("未知任务状态: status=%s task_data=%s", status, task_data)

        raise TimeoutError(f"Filmate 视频任务轮询超时: task_id={task_id}")

    @staticmethod
    @with_retry_async(
        max_attempts=DOWNLOAD_MAX_ATTEMPTS,
        backoff_seconds=DOWNLOAD_BACKOFF_SECONDS,
        retry_if=lambda e: (
            (isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (400, 403, 404))
            or isinstance(e, httpx.ConnectTimeout)
            or isinstance(e, httpx.ReadTimeout)
        ),
    )
    async def _download_video_with_retry(video_url: str, output_path: Path) -> None:
        """下载视频到本地。"""
        await download_video(video_url, output_path)
        logger.info("Filmate 视频已下载: %s", output_path)

    @staticmethod
    def _normalize_base_url(url: str | None) -> str | None:
        """规范化 Filmate API 的 base_url。

        Filmate API 路径结构为 /api/v1，
        需要确保 base_url 包含此路径前缀。
        """
        if not url:
            return None
        url = url.strip().rstrip("/")
        # 如果已经包含 /api/v1，直接返回
        if url.endswith("/api/v1") or url.endswith("/api/v1/"):
            return url
        # 如果是 sk.aistore777.top 基础域名，添加 /api/v1
        if "sk.aistore777.top" in url:
            if url.endswith("/api"):
                return url
            if "/api/" not in url and "/v1" not in url:
                url += "/api/v1"
        return url

    def _build_files_url(self, file_path: Path, project_name: str | None = None) -> str | None:
        """Build a URL the filmate backend can fetch.

        Uses ``media_storage.media_url_for`` to get a signed CDN URL whenever
        Qiniu is enabled — the URL is public HTTPS, expires in 1h, and points
        at the actual stored object (``projects_test/...`` key), so filmate
        can fetch it without any auth.

        Falls back to the legacy ``FILMATE_FILES_BASE_URL`` splice if Qiniu
        is disabled (local dev).
        """
        from urllib.parse import quote

        path_str = str(file_path)

        rel_path: str | None = None
        for pattern in ("/projects/", "/deploy/projects/"):
            idx = path_str.find(pattern)
            if idx != -1:
                rel_path = path_str[idx + len(pattern):]
                break

        # 1) Qiniu signed CDN URL — works without any auth on the filmate side
        if rel_path is not None:
            try:
                from lib.media_storage import get_media_storage

                storage = get_media_storage()
                if storage.enabled:
                    proj = project_name or rel_path.split("/", 1)[0]
                    return storage.media_url_for(proj, rel_path)
            except Exception as exc:  # pragma: no cover
                logger.debug("media_storage URL build failed, fallback: %s", exc)

        # 2) Legacy FILMATE_FILES_BASE_URL splice (local dev only)
        if not self._files_base_url:
            logger.debug(
                "FILMATE_FILES_BASE_URL unset and media_storage disabled; cannot build URL: %s",
                path_str,
            )
            return None
        if rel_path is None:
            logger.warning("Cannot extract project-relative path from: %s", path_str)
            return None
        encoded_path = quote(rel_path, safe="/")
        url = f"{self._files_base_url.rstrip('/')}/files/{encoded_path}"
        logger.info("Built file URL: path=%s -> url=%s", path_str, url)
        return url

        # 从文件路径中提取相对于项目目录的路径
        # 例如：/home/Ai/filmate/deploy/projects/proj-9966a4b0/reference_videos/temp/xxx.jpg
        # 或：/app/projects/proj-9966a4b0/reference_videos/temp/xxx.jpg

        path_str = str(file_path)

        # 尝试匹配项目目录模式
        for pattern in ("/projects/", "/deploy/projects/"):
            idx = path_str.find(pattern)
            if idx != -1:
                # 提取 {project_name}/... 部分
                rel_path = path_str[idx + len(pattern) :]
                # URL 编码特殊字符（中文等）
                from urllib.parse import quote

                encoded_path = quote(rel_path, safe="/")
                url = f"{self._files_base_url.rstrip('/')}/files/{encoded_path}"
                logger.info("构建文件 URL: path=%s -> url=%s", path_str, url)
                return url

        logger.warning("无法从路径提取项目名称: %s", path_str)
        return None

    def _ensure_full_url(self, url: str) -> str:
        """确保 URL 是完整的 HTTP URL。

        Filmate API 可能返回相对路径（如 /video/xxx.mp4），
        需要补充 base URL 前缀。
        """
        if not url:
            raise ValueError("URL 不能为空")
        url = url.strip()
        # 如果已经是完整 URL，直接返回
        if url.startswith("http://") or url.startswith("https://"):
            return url
        # 相对路径：提取 base URL 的协议和域名部分
        from urllib.parse import urlparse

        parsed = urlparse(self._base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        # 确保相对路径以 / 开头
        if not url.startswith("/"):
            url = "/" + url
        return base + url

    def _parse_result_url(self, result: str) -> str:
        """解析 API 返回的 result 字段。

        Filmate API 可能返回：
        1. 直接的 URL 字符串: "https://..."
        2. JSON 数组字符串: "[\"https://...\"]"
        3. JSON 对象字符串: "{\"url\": \"https://...\"}"

        本方法统一解析为直接 URL 字符串。
        """
        if not result:
            raise ValueError("result 不能为空")
        result = result.strip()

        # 如果是直接的 HTTP URL，直接返回
        if result.startswith("http://") or result.startswith("https://"):
            return result

        # 尝试解析为 JSON
        import json

        try:
            parsed = json.loads(result)
            # 如果是数组，取第一个元素
            if isinstance(parsed, list):
                if not parsed:
                    raise ValueError(f"result 数组为空: {result}")
                return str(parsed[0])
            # 如果是对象，尝试常见字段名
            if isinstance(parsed, dict):
                for key in ("url", "result", "image", "video", "output"):
                    if key in parsed:
                        return str(parsed[key])
                raise ValueError(f"result 对象不含已知字段: {result}")
            # 其他类型转为字符串
            return str(parsed)
        except json.JSONDecodeError:
            # 不是 JSON，原样返回
            return result

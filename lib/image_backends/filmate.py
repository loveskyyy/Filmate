"""FilmateImageBackend — Filmate 图片生成后端。

基于 OpenAI 兼容 API，支持 T2I 和 I2I，使用任务轮询模式获取结果。
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


def _map_resolution(resolution: str | None) -> str | None:
    """映射分辨率字符串。"""
    if resolution is None:
        return None
    # resolution 参数直接透传，API 支持 "4K"
    return resolution


def _map_aspect_ratio(aspect_ratio: str) -> str:
    """映射宽高比字符串。"""
    # API 支持: 1:1、2:3、3:2、16:9、9:16
    return aspect_ratio


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
        # 规范化 base_url，确保包含 /api/v1 路径
        self._base_url = self._normalize_base_url(base_url) or DEFAULT_BASE_URL
        self._model = model or DEFAULT_MODEL
        # 下载超时设置为 120 秒，因为图片存储服务可能较慢
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
        payload["size"] = _map_aspect_ratio(aspect_ratio)

        # 处理分辨率
        if request.image_size:
            resolution = _map_resolution(request.image_size)
            if resolution:
                payload["resolution"] = resolution

        # 处理参考图
        if has_refs:
            ref_urls = [ref.path for ref in request.reference_images]
            if len(ref_urls) == 1:
                payload["reference_image"] = ref_urls[0]
            else:
                payload["reference_images"] = ref_urls

        # 提交任务
        logger.info(
            "提交 Filmate 图片生成任务 (T2I) kwargs=%s, base_url=%s",
            format_kwargs_for_log(payload),
            self._base_url,
        )

        submit_url = f"{self._base_url}/images/generations"
        response = await self._client.post(submit_url, json=payload, headers=headers)
        response.raise_for_status()

        result = response.json()
        if result.get("code") != 200:
            raise RuntimeError(f"Filmate 图片提交失败: {result}")

        task_data = result.get("data", {})
        task_id = task_data.get("task_id")
        if not task_id:
            raise RuntimeError(f"Filmate 响应缺少 task_id: {result}")

        logger.info("Filmate 图片任务已提交: task_id=%s", task_id)

        # 轮询获取结果
        result_url = await self._poll_task_result(task_id, headers)

        # 下载并保存图片
        output_path = await self._download_and_save(result_url, request.output_path)

        return ImageGenerationResult(
            image_path=output_path,
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
                result_url = task_data.get("result")
                if not result_url:
                    raise RuntimeError(f"Filmate 任务成功但无 result: {task_data}")
                # 解析 JSON 数组字符串（如果 API 返回的是 ["url"] 格式）
                result_url = self._parse_result_url(result_url)
                # 确保 result_url 是完整的 HTTP URL
                result_url = self._ensure_full_url(result_url)
                logger.info("Filmate 图片任务完成: task_id=%s result_url=%s", task_id, result_url)
                return result_url

            elif status == _TASK_STATUS_FAILED:
                error_msg = task_data.get("error", "未知错误")
                raise RuntimeError(f"Filmate 图片生成失败: {error_msg}")

            elif status in (_TASK_STATUS_PENDING, _TASK_STATUS_PROCESSING, _TASK_STATUS_SUBMITTED):
                logger.debug("轮询 Filmate 图片任务: task_id=%s status=%s attempt=%d", task_id, status, attempt)
                continue

            else:
                logger.warning("未知任务状态: status=%s task_data=%s", status, task_data)

        raise TimeoutError(f"Filmate 图片任务轮询超时: task_id={task_id}")

    @with_retry_async(max_attempts=3, backoff_seconds=(2, 4, 8))
    async def _download_and_save(self, url: str, output_path: Path) -> Path:
        """下载图片并保存到指定路径。"""
        logger.info("开始下载图片: url=%s", url)
        response = await self._client.get(url)
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)

        logger.info("Filmate 图片已保存: %s", output_path)
        return output_path

    async def _get_image_size(self, path: Path) -> tuple[int, int]:
        """获取图片尺寸。"""
        from PIL import Image

        img = Image.open(path)
        return img.size

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

    def _ensure_full_url(self, url: str) -> str:
        """确保 URL 是完整的 HTTP URL。

        Filmate API 可能返回相对路径（如 /image/xxx.png），
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

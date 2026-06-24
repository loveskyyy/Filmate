"""FilmateTextBackend — Filmate 文本生成后端。

基于 OpenAI 兼容 Chat Completions API，使用任务轮询模式获取结果。
"""

from __future__ import annotations

import asyncio
import logging

from lib.logging_utils import format_kwargs_for_log
from lib.providers import PROVIDER_FILMATE
from lib.retry import with_retry_async
from lib.text_backends.base import (
    TextBackend,
    TextCapability,
    TextGenerationRequest,
    TextGenerationResult,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://sk.aistore777.top/api/v1"
DEFAULT_MODEL = "Gemini 3.1 Pro"

# 任务状态码
_TASK_STATUS_PENDING = 0
_TASK_STATUS_SUCCESS = 1
_TASK_STATUS_FAILED = 2
_TASK_STATUS_PROCESSING = 3
_TASK_STATUS_SUBMITTED = 4

# 重试配置
_POLL_INTERVAL = 1.0  # 秒
_MAX_POLL_ATTEMPTS = 60  # 最多等待 60 秒


class FilmateTextBackend(TextBackend):
    """Filmate 文本生成后端，使用任务轮询模式。"""

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
        self._client = httpx.AsyncClient(timeout=60.0)
        self._capabilities: set[TextCapability] = {
            TextCapability.TEXT_GENERATION,
            TextCapability.STRUCTURED_OUTPUT,
            TextCapability.VISION,
        }

    @property
    def name(self) -> str:
        return PROVIDER_FILMATE

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return self._capabilities

    @with_retry_async(max_attempts=4, backoff_seconds=(2, 4, 8))
    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        """生成文本回复，使用任务提交 + 轮询模式。"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # 构建消息
        messages = self._build_messages(request)

        # 构建请求体
        payload: dict = {
            "model": self._model,
            "prompt": messages[0]["content"] if messages else request.prompt,
        }

        # 处理 max_tokens
        if request.max_output_tokens is not None:
            payload["token_count"] = request.max_output_tokens

        logger.info(
            "提交 Filmate 文本生成任务 kwargs=%s",
            format_kwargs_for_log({"model": payload["model"], "token_count": payload.get("token_count")}),
        )

        # 提交任务
        submit_url = f"{self._base_url}/openai/chat/completions"
        response = await self._client.post(submit_url, json=payload, headers=headers)
        response.raise_for_status()

        result = response.json()
        if result.get("code") != 200:
            raise RuntimeError(f"Filmate 文本提交失败: {result}")

        task_data = result.get("data", {})
        task_id = task_data.get("task_id")
        if not task_id:
            raise RuntimeError(f"Filmate 响应缺少 task_id: {result}")

        logger.info("Filmate 文本任务已提交: task_id=%s", task_id)

        # 轮询获取结果
        text = await self._poll_task_result(task_id, headers)

        return TextGenerationResult(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=None,
            output_tokens=None,
        )

    def _build_messages(self, request: TextGenerationRequest) -> list[dict]:
        """构建消息列表。"""
        messages: list[dict] = []

        # 系统消息
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        # 用户消息
        if request.prompt:
            messages.append({"role": "user", "content": request.prompt})

        return messages

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
                text = task_data.get("result")
                if text is None:
                    raise RuntimeError(f"Filmate 任务成功但无 result: {task_data}")
                logger.info("Filmate 文本任务完成: task_id=%s", task_id)
                return text

            elif status == _TASK_STATUS_FAILED:
                error_msg = task_data.get("error", "未知错误")
                raise RuntimeError(f"Filmate 文本生成失败: {error_msg}")

            elif status in (_TASK_STATUS_PENDING, _TASK_STATUS_PROCESSING, _TASK_STATUS_SUBMITTED):
                logger.debug("轮询 Filmate 文本任务: task_id=%s status=%s attempt=%d", task_id, status, attempt)
                continue

            else:
                logger.warning("未知任务状态: status=%s task_data=%s", status, task_data)

        raise TimeoutError(f"Filmate 文本任务轮询超时: task_id={task_id}")

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

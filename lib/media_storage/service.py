"""七牛云 Kodo 项目存储。

项目文件始终使用项目内相对路径。七牛启用时，项目持久化文件映射到确定性的
Kodo object key；本地目录是供现有同步代码、ffmpeg 和导出流程使用的工作副本。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import re
import shutil
import tempfile
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import urlopen

import logging

logger = logging.getLogger(__name__)

import portalocker

from lib.app_data_dir import app_data_dir

_MEDIA_SUFFIXES = frozenset(
    {
        ".aac",
        ".avif",
        ".flac",
        ".gif",
        ".heic",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".ogg",
        ".opus",
        ".png",
        ".tif",
        ".tiff",
        ".wav",
        ".webm",
        ".webp",
    }
)
_CACHE_INDEX_NAME = ".media-cache-index.json"
_BATCH_DELETE_MAX_KEYS = 1000
_PROJECT_RUNTIME_FILES = frozenset({"CLAUDE.md"})
_PROJECT_RUNTIME_PARTS = frozenset({"__MACOSX"})
_PROJECT_RUNTIME_SUFFIXES = frozenset({".bak", ".lock", ".part", ".temp", ".tmp"})
_PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class MediaStorageError(RuntimeError):
    """云端项目文件上传、物化或删除失败。"""


class MediaStorageConfigurationError(MediaStorageError):
    """启用七牛存储但部署配置不完整。"""


class MediaStorageNotFoundError(MediaStorageError):
    """远端对象不存在 (HTTP 404 / NoSuchKey)。

    上层读路径可据此把"资源本就不存在"和"网络/权限/服务异常"区分开：
    前者通常对应"还没生成"或"已删除"，业务上应当降级（按空处理），
    不应该让请求整体 5xx。
    """


def _env_flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise MediaStorageConfigurationError(f"{name} 必须是正整数") from exc
    if value <= 0:
        raise MediaStorageConfigurationError(f"{name} 必须是正整数")
    return value


@dataclass(frozen=True)
class MediaStorageConfig:
    enabled: bool
    access_key: str = ""
    secret_key: str = ""
    bucket: str = ""
    domain: str = ""
    object_prefix: str = "projects"
    upload_token_ttl_seconds: int = 3600
    download_url_ttl_seconds: int = 3600
    cache_max_bytes: int = 20 * 1024 * 1024 * 1024

    @classmethod
    def from_environment(cls) -> MediaStorageConfig:
        enabled = _env_flag(os.environ.get("QINIU_ENABLED"))
        config = cls(
            enabled=enabled,
            access_key=os.environ.get("QINIU_ACCESS_KEY", "").strip(),
            secret_key=os.environ.get("QINIU_SECRET_KEY", "").strip(),
            bucket=os.environ.get("QINIU_BUCKET", "").strip(),
            domain=os.environ.get("QINIU_DOMAIN", "").strip().rstrip("/"),
            object_prefix=os.environ.get("QINIU_OBJECT_PREFIX", "projects").strip().strip("/"),
            upload_token_ttl_seconds=_env_positive_int("QINIU_UPLOAD_TOKEN_TTL_SECONDS", 3600),
            download_url_ttl_seconds=_env_positive_int("QINIU_DOWNLOAD_URL_TTL_SECONDS", 3600),
            cache_max_bytes=_env_positive_int("QINIU_MEDIA_CACHE_MAX_BYTES", 20 * 1024 * 1024 * 1024),
        )
        if not enabled:
            return config

        missing = [
            name
            for name, value in (
                ("QINIU_ACCESS_KEY", config.access_key),
                ("QINIU_SECRET_KEY", config.secret_key),
                ("QINIU_BUCKET", config.bucket),
                ("QINIU_DOMAIN", config.domain),
            )
            if not value
        ]
        if missing:
            raise MediaStorageConfigurationError(f"启用七牛项目存储时必须设置: {', '.join(missing)}")
        if not config.object_prefix:
            raise MediaStorageConfigurationError("QINIU_OBJECT_PREFIX 不能为空")
        try:
            MediaStorage._normalize_relative(config.object_prefix)
        except ValueError as exc:
            raise MediaStorageConfigurationError("QINIU_OBJECT_PREFIX 不合法") from exc
        if config.domain.startswith("http://"):
            raise MediaStorageConfigurationError("QINIU_DOMAIN 必须使用 HTTPS")
        return config


class MediaStorage:
    """以项目内路径为协议的七牛私有对象存储。"""

    def __init__(self, config: MediaStorageConfig, data_root: Path):
        self.config = config
        self.data_root = Path(data_root).resolve()
        self._auth: Any | None = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @staticmethod
    def _normalize_relative(relative_path: str | Path) -> str:
        raw = str(relative_path).replace("\\", "/").strip()
        path = PurePosixPath(raw)
        if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"非法项目相对路径: {relative_path}")
        if ":" in path.parts[0]:
            raise ValueError(f"非法项目相对路径: {relative_path}")
        return path.as_posix()

    @staticmethod
    def is_media_relative_path(relative_path: str | Path) -> bool:
        try:
            normalized = MediaStorage._normalize_relative(relative_path)
        except ValueError:
            return False
        path = PurePosixPath(normalized)
        return MediaStorage.is_project_relative_path(normalized) and path.suffix.lower() in _MEDIA_SUFFIXES

    @staticmethod
    def is_project_relative_path(relative_path: str | Path) -> bool:
        """判断项目内路径是否属于应持久化到对象存储的业务文件。"""
        try:
            normalized = MediaStorage._normalize_relative(relative_path)
        except ValueError:
            return False
        path = PurePosixPath(normalized)
        if any(part.startswith(".") or part in _PROJECT_RUNTIME_PARTS for part in path.parts):
            return False
        if path.name in _PROJECT_RUNTIME_FILES or path.suffix.lower() in _PROJECT_RUNTIME_SUFFIXES:
            return False
        return not path.name.startswith("project.json.bak.")

    def _resolve_under(self, root: Path, relative_path: str | Path) -> tuple[Path, str]:
        normalized = self._normalize_relative(relative_path)
        resolved_root = root.resolve()
        # Windows 对已存在的根目录和不存在的子路径可能产生不同的 extended-path
        # 表示；先从已解析根目录构造，确保后续包含关系比较使用同一种表示。
        candidate = (resolved_root / normalized).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"项目路径越界: {relative_path}") from exc
        return candidate, normalized

    def _object_key(self, *parts: str) -> str:
        return "/".join((self.config.object_prefix, *parts))

    @staticmethod
    def _normalize_project_name(project_name: str) -> str:
        normalized = MediaStorage._normalize_relative(project_name)
        if len(PurePosixPath(normalized).parts) != 1 or not _PROJECT_NAME_PATTERN.fullmatch(normalized):
            raise ValueError(f"非法项目名称: {project_name}")
        return normalized

    def project_object_key(self, project_name: str, relative_path: str | Path) -> str:
        project_name = self._normalize_project_name(project_name)
        normalized = self._normalize_relative(relative_path)
        if not self.is_project_relative_path(normalized):
            raise ValueError(f"不是受管项目路径: {relative_path}")
        return self._object_key(project_name, normalized)

    def global_object_key(self, relative_path: str | Path) -> str:
        normalized = self._normalize_relative(relative_path)
        if not normalized.startswith("_global_assets/") or not self.is_media_relative_path(normalized):
            raise ValueError(f"不是受管全局媒体路径: {relative_path}")
        return self._object_key(normalized)

    def _qiniu_auth(self) -> Any:
        if self._auth is None:
            from qiniu import Auth

            self._auth = Auth(self.config.access_key, self.config.secret_key)
        return self._auth

    def _object_url(self, object_key: str) -> str:
        domain = self.config.domain
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"
        return f"{domain.rstrip('/')}/{quote(object_key, safe='/')}"

    def _object_lock_path(self, object_key: str) -> Path:
        digest = hashlib.sha256(object_key.encode("utf-8")).hexdigest()
        return self.data_root / ".media-locks" / f"{digest}.lock"

    def signed_url_for_key(self, object_key: str) -> str:
        if not self.enabled:
            raise MediaStorageConfigurationError("七牛媒体存储未启用")
        return self._qiniu_auth().private_download_url(
            self._object_url(object_key),
            expires=self.config.download_url_ttl_seconds,
        )

    def signed_project_url(self, project_name: str, relative_path: str | Path) -> str:
        return self.signed_url_for_key(self.project_object_key(project_name, relative_path))

    def media_url_for(self, project_name: str, relative_path: str | Path) -> str:
        """Return the best URL the browser should use to fetch a project asset.

        Qiniu enabled (production) -> return a signed CDN URL the browser can
        fetch directly. 1 hop, no proxy.
        Qiniu disabled (local dev) -> return the local `/api/v1/files/...` proxy
        URL; the FastAPI endpoint serves the file from local disk.
        """
        if self.enabled:
            return self.signed_project_url(project_name, relative_path)
        cleaned = str(relative_path).lstrip("/")
        return f"/api/v1/files/{project_name}/{cleaned}"

    def signed_global_url(self, relative_path: str | Path) -> str:
        return self.signed_url_for_key(self.global_object_key(relative_path))

    def _upload_file(self, source_path: Path, object_key: str) -> None:
        """使用官方 SDK 上传，并以七牛 ETag 验证远端内容。

        大文件走 SDK 分片（4MB/片），默认单片 60s 超时——大文件单次上传可能跨多片，
        任一片超时或网络抖动都导致整体失败。我们包 3 次重试（指数退避 1s/2s/4s）以
        防伴随网络抖动；raise 前打印 status_code + body + elapsed，避免之前一个推不
        动的 generic "MediaStorageError" 把真正原因吞掉。
        """
        import time as _time
        from qiniu import etag, put_file_v2

        token = self._qiniu_auth().upload_token(
            self.config.bucket,
            object_key,
            self.config.upload_token_ttl_seconds,
            policy={"returnBody": '{"key":"$(key)","hash":"$(etag)"}'},
        )
        mime_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        # 实测发现阿里云 ECS -> 七牛华东的上行带宽在某些时段被卡到 ~50KB/s，5.7MB 视频文件
        # 单次上传需要 120s+。qiniu SDK 默认 connection_timeout=30s + 单片 60s 早早就 timeout
        # 了。三步修复：
        # 1) qiniu.config.set_default 把 connection_timeout 拉到 600s（只在本进程内生效，
        #    副作用小）
        # 2) put_file_v2 显式传 part_size=4MB（qiniu.etag() 默认 4MB，必须一致才能校验通过）
        # 3) 重试间隔 5/15/45s，最多 3 次（共 65s 等待 + 多次 600s 尝试 = 充足）
        from qiniu import config as _qiniu_config, put_file_v2
        _qiniu_config.set_default(connection_timeout=600)
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                t0 = _time.monotonic()
                result, info = put_file_v2(
                    token,
                    object_key,
                    str(source_path),
                    mime_type=mime_type,
                    version="v2",
                    bucket_name=self.config.bucket,
                    part_size=4 * 1024 * 1024,  # 4MB, MUST match qiniu.etag() default
                )
                elapsed = _time.monotonic() - t0
                sc = getattr(info, "status_code", 0)
                body = (getattr(info, "text_body", None) or "")[:400]
                req_id = getattr(info, "req_id", None)
                if not result or sc != 200:
                    raise MediaStorageError(
                        f"七牛上传失败: status={sc} req_id={req_id} elapsed={elapsed:.1f}s "
                        f"object_key={object_key} body={body}"
                    )
                if result.get("key") != object_key or result.get("hash") != etag(str(source_path)):
                    raise MediaStorageError(
                        f"七牛上传校验失败: object_key={object_key} "
                        f"result_key={result.get('key')!r} result_hash={result.get('hash')!r}"
                    )
                return
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "七牛上传尝试 %d/3 失败: object_key=%s exc=%s",
                    attempt, object_key, exc,
                )
                if attempt < 3:
                    _time.sleep(5 * (3 ** (attempt - 1)))  # 5/15/45s
        raise last_exc if last_exc else MediaStorageError("七牛项目文件上传失败")

    def sync_project_paths(
        self,
        project_path: Path,
        relative_paths: Iterable[str | Path],
        *,
        object_project_name: str | None = None,
        preserve_local_on_failure: bool = False,
    ) -> None:
        if not self.enabled:
            return
        project_path = Path(project_path).resolve()
        object_project_name = self._normalize_project_name(object_project_name or project_path.name)
        synced_paths: list[Path] = []
        for relative_path in relative_paths:
            source_path, normalized = self._resolve_under(project_path, relative_path)
            if not self.is_project_relative_path(normalized):
                continue
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            object_key = self.project_object_key(object_project_name, normalized)
            try:
                self._upload_file(source_path, object_key)
            except Exception as upload_exc:
                if preserve_local_on_failure:
                    raise
                # 清晰定位：上传失败时只检查远端是否已存在同名对象。
                # - 远端不在 → 不动本地（不要 unlink、不要 materialize），让未来后台 retry
                #   worker / 用户手动触发重试能复用这个本地文件，避免云端重新计费生成
                #   （如 filmate 视频生成价格高）。这样 E1U01 那种"Filmate 后台已经生
                #   成但上传到七牛失败"的场景，本地源文件不会被吞掉，retry 一次就能救
                #   回，避免双重扣费。
                # - 远端存在 → 强制走一次 materialize 以保证本地与云端一致（原来的行为）。
                rollback_exc: Exception | None = None
                try:
                    remote_info = self.project_file_info(object_project_name, normalized)
                    if remote_info is not None:
                        self._materialize(
                            source_path,
                            object_key,
                            track_cache=self.is_media_relative_path(normalized),
                            force=True,
                        )
                except Exception as exc:
                    rollback_exc = exc
                if rollback_exc is not None:
                    upload_exc.add_note(f"本地与云端一致化失败: {type(rollback_exc).__name__}")
                raise upload_exc
            if self.is_media_relative_path(normalized):
                synced_paths.append(source_path)
        self._record_cache_entries(synced_paths)
        self.evict_local_cache()

    def sync_project_files(
        self,
        project_path: Path,
        *,
        object_project_name: str | None = None,
        preserve_local_on_failure: bool = False,
    ) -> None:
        """上传项目目录内全部持久化业务文件，可用于导入或迁移。"""
        if not self.enabled:
            return
        project_path = Path(project_path).resolve()
        relative_paths = [
            path.relative_to(project_path).as_posix()
            for path in sorted(project_path.rglob("*"))
            if path.is_file() and self.is_project_relative_path(path.relative_to(project_path).as_posix())
        ]
        self.sync_project_paths(
            project_path,
            relative_paths,
            object_project_name=object_project_name,
            preserve_local_on_failure=preserve_local_on_failure,
        )

    def snapshot_project_files(self, project_path: Path) -> dict[str, tuple[int, int]]:
        """记录项目业务文件签名，供 Agent 等直接文件写入链路做回合后对账。"""
        project_path = Path(project_path).resolve()
        snapshot: dict[str, tuple[int, int]] = {}
        for path in sorted(project_path.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(project_path).as_posix()
            if not self.is_project_relative_path(relative):
                continue
            stat = path.stat()
            snapshot[relative] = (stat.st_size, stat.st_mtime_ns)
        return snapshot

    def reconcile_project_files(self, project_path: Path, before: dict[str, tuple[int, int]]) -> None:
        """同步快照后新增/修改文件，并删除快照后消失的远端对象。"""
        if not self.enabled:
            return
        project_path = Path(project_path).resolve()
        after = self.snapshot_project_files(project_path)
        changed = [path for path, signature in after.items() if before.get(path) != signature]
        removed = [path for path in before if path not in after]
        if changed:
            self.sync_project_paths(project_path, changed)
        if removed:
            try:
                self.delete_project_paths(project_path.name, removed)
            except Exception as delete_exc:
                rollback_errors: list[str] = []
                for relative_path in removed:
                    try:
                        self.materialize_project_file(project_path, relative_path, force=True)
                    except Exception as exc:
                        rollback_errors.append(f"{relative_path}: {type(exc).__name__}")
                if rollback_errors:
                    delete_exc.add_note("本地删除回滚失败: " + ", ".join(rollback_errors))
                raise

    def sync_project_media(self, project_path: Path, *, object_project_name: str | None = None) -> None:
        """上传项目目录内全部受管媒体，可用于尚未安装的导入暂存目录。"""
        if not self.enabled:
            return
        project_path = Path(project_path).resolve()
        relative_paths = [
            path.relative_to(project_path).as_posix()
            for path in sorted(project_path.rglob("*"))
            if path.is_file() and self.is_media_relative_path(path.relative_to(project_path).as_posix())
        ]
        self.sync_project_paths(
            project_path,
            relative_paths,
            object_project_name=object_project_name,
        )

    def sync_global_paths(self, relative_paths: Iterable[str | Path]) -> None:
        if not self.enabled:
            return
        synced_paths: list[Path] = []
        for relative_path in relative_paths:
            source_path, normalized = self._resolve_under(self.data_root, relative_path)
            if not normalized.startswith("_global_assets/") or not self.is_media_relative_path(normalized):
                continue
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            self._upload_file(source_path, self.global_object_key(normalized))
            synced_paths.append(source_path)
        self._record_cache_entries(synced_paths)
        self.evict_local_cache()

    async def sync_project_paths_async(self, project_path: Path, relative_paths: Iterable[str | Path]) -> None:
        await asyncio.to_thread(self.sync_project_paths, project_path, list(relative_paths))

    async def delete_project_paths_async(
        self,
        project_name: str,
        relative_paths: Iterable[str | Path],
    ) -> None:
        await asyncio.to_thread(self.delete_project_paths, project_name, list(relative_paths))

    async def sync_global_paths_async(self, relative_paths: Iterable[str | Path]) -> None:
        await asyncio.to_thread(self.sync_global_paths, list(relative_paths))

    def materialize_project_file(
        self,
        project_path: Path,
        relative_path: str | Path,
        *,
        force: bool = False,
    ) -> Path:
        project_path = Path(project_path).resolve()
        target_path, normalized = self._resolve_under(project_path, relative_path)
        if target_path.is_file() and not force:
            if self.enabled and self.is_media_relative_path(normalized):
                self._record_cache_entries([target_path])
            return target_path
        if not self.enabled or not self.is_project_relative_path(normalized):
            return target_path
        self._materialize(
            target_path,
            self.project_object_key(project_path.name, normalized),
            track_cache=self.is_media_relative_path(normalized),
            force=force,
        )
        return target_path

    def materialize_global_file(self, relative_path: str | Path) -> Path:
        target_path, normalized = self._resolve_under(self.data_root, relative_path)
        if target_path.is_file():
            if self.enabled and self.is_media_relative_path(normalized):
                self._record_cache_entries([target_path])
            return target_path
        if not self.enabled or not normalized.startswith("_global_assets/"):
            return target_path
        if not self.is_media_relative_path(normalized):
            return target_path
        self._materialize(target_path, self.global_object_key(normalized), track_cache=True)
        return target_path

    def _materialize(self, target_path: Path, object_key: str, *, track_cache: bool, force: bool = False) -> None:
        key = str(target_path)
        with _LOCKS_GUARD:
            lock = _LOCKS.setdefault(key, threading.Lock())
        with lock:
            lock_path = self._object_lock_path(object_key)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with portalocker.Lock(lock_path, timeout=60):
                    if target_path.is_file() and not force:
                        return
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    temp_path: Path | None = None
                    try:
                        with tempfile.NamedTemporaryFile(dir=target_path.parent, delete=False) as temp_file:
                            temp_path = Path(temp_file.name)
                            try:
                                with urlopen(self.signed_url_for_key(object_key), timeout=30) as response:
                                    shutil.copyfileobj(response, temp_file)
                            except HTTPError as exc:
                                # 404 (NoSuchKey / Document not found) 在七牛 Kodo 是
                                # 资源根本不存在的标准响应——必须和"权限/限速/CDN 异常"区分。
                                if exc.code == 404:
                                    raise MediaStorageNotFoundError(
                                        f"七牛对象不存在: {object_key}"
                                    ) from exc
                                raise
                        if not temp_path.stat().st_size:
                            raise MediaStorageError("七牛项目文件下载结果为空")
                        temp_path.replace(target_path)
                        if track_cache:
                            self._record_cache_entries([target_path])
                            self.evict_local_cache(exclude={target_path})
                    finally:
                        if temp_path is not None:
                            temp_path.unlink(missing_ok=True)
            except MediaStorageError:
                raise
            except Exception as exc:
                raise MediaStorageError("七牛项目文件下载失败") from exc

    def _list_object_keys(self, prefix: str) -> list[str]:
        """列举前缀下的对象；失败时不将不完整项目伪装成可导出。"""
        from qiniu import BucketManager

        manager = BucketManager(self._qiniu_auth())
        marker: str | None = None
        keys: list[str] = []
        try:
            while True:
                result, eof, info = manager.list(self.config.bucket, prefix, marker, 1000, None)
                if getattr(info, "status_code", 0) != 200 or not isinstance(result, dict):
                    raise MediaStorageError("七牛项目文件列表读取失败")
                items = result.get("items", [])
                if not isinstance(items, list):
                    raise MediaStorageError("七牛项目文件列表响应无效")
                keys.extend(
                    item["key"] for item in items if isinstance(item, dict) and isinstance(item.get("key"), str)
                )
                if eof:
                    return keys
                marker = result.get("marker")
                if not isinstance(marker, str) or not marker:
                    raise MediaStorageError("七牛项目文件列表响应缺少分页标记")
        except MediaStorageError:
            raise
        except Exception as exc:
            raise MediaStorageError("七牛项目文件列表读取失败") from exc

    def _list_common_prefixes(self, prefix: str) -> list[str]:
        """列举一级公共前缀，用于在无本地工作副本时发现远端项目。"""
        from qiniu import BucketManager

        manager = BucketManager(self._qiniu_auth())
        marker: str | None = None
        prefixes: list[str] = []
        try:
            while True:
                result, eof, info = manager.list(self.config.bucket, prefix, marker, 1000, "/")
                if getattr(info, "status_code", 0) != 200 or not isinstance(result, dict):
                    raise MediaStorageError("七牛项目列表读取失败")
                common_prefixes = result.get("commonPrefixes", [])
                if not isinstance(common_prefixes, list):
                    raise MediaStorageError("七牛项目列表响应无效")
                prefixes.extend(item for item in common_prefixes if isinstance(item, str))
                if eof:
                    return prefixes
                marker = result.get("marker")
                if not isinstance(marker, str) or not marker:
                    raise MediaStorageError("七牛项目列表响应缺少分页标记")
        except MediaStorageError:
            raise
        except Exception as exc:
            raise MediaStorageError("七牛项目列表读取失败") from exc

    def _object_info(self, object_key: str) -> dict[str, Any] | None:
        """读取对象元数据；不存在返回 None，认证或网络错误显式失败。"""
        if not self.enabled:
            return None

        from qiniu import BucketManager

        try:
            response: Any = BucketManager(self._qiniu_auth()).stat(self.config.bucket, object_key)
        except Exception as exc:
            raise MediaStorageError("七牛项目文件状态读取失败") from exc
        if not isinstance(response, tuple) or len(response) != 2:
            raise MediaStorageError("七牛项目文件状态读取失败")
        result, info = response
        status_code = getattr(info, "status_code", 0)
        if status_code == 200 and isinstance(result, dict):
            return result
        if status_code in {404, 612}:
            return None
        raise MediaStorageError("七牛项目文件状态读取失败")

    def project_file_info(self, project_name: str, relative_path: str | Path) -> dict[str, Any] | None:
        """读取项目对象元数据；不存在返回 None，认证或网络错误显式失败。"""
        return self._object_info(self.project_object_key(project_name, relative_path))

    def global_file_info(self, relative_path: str | Path) -> dict[str, Any] | None:
        """读取全局资产对象元数据；不存在返回 None，认证或网络错误显式失败。"""
        return self._object_info(self.global_object_key(relative_path))

    def project_file_exists(self, project_name: str, relative_path: str | Path) -> bool:
        """检查项目对象是否存在；认证或网络错误必须显式失败。"""
        return self.project_file_info(project_name, relative_path) is not None

    def project_asset_exists(self, project_name: str, relative_path: str | Path) -> bool:
        """判断一个项目内资产是否已生成且可服务（cloud-aware）。

        Qiniu 启用（生产云端唯一模式）→ 走 Qiniu stat，不依赖本地是否物化。
        Qiniu 未启用（本地 dev）→ 走本地文件存在性。

        用途：status_calculator 计 characters/scenes/props 已生成数，
        episode_ledger 判断是否有下游产物，等等。云端唯一模式下，
        media 文件不会自动物化，旧的 ``safe_exists(project_dir, ...)``
        会一直返回 False，导致「已生成但显示待生成」误报。
        """
        try:
            normalized = self._normalize_relative(relative_path)
        except ValueError:
            return False
        if self.enabled and self.is_project_relative_path(normalized):
            return self.project_file_exists(project_name, normalized)
        from lib.path_safety import safe_exists
        project_dir = self.data_root / "projects" / self._normalize_project_name(project_name)
        return safe_exists(project_dir, normalized)

    def list_project_names(self) -> list[str]:
        """列出包含 project.json 的远端项目名称。"""
        if not self.enabled:
            return []
        root_prefix = f"{self.config.object_prefix}/"
        names: list[str] = []
        for common_prefix in self._list_common_prefixes(root_prefix):
            if not common_prefix.startswith(root_prefix):
                continue
            relative = common_prefix.removeprefix(root_prefix).strip("/")
            try:
                name = self._normalize_project_name(relative)
            except ValueError:
                continue
            if name.startswith("_"):
                continue
            if self.project_file_exists(name, "project.json"):
                names.append(name)
        return sorted(dict.fromkeys(names))

    def materialize_project_data(self, project_path: Path) -> None:
        """物化并对账项目非媒体业务文件；媒体仍由具体处理链按需下载。"""
        project_path = Path(project_path).resolve()
        if not self.enabled:
            return
        project_name = self._normalize_project_name(project_path.name)
        prefix = f"{self._object_key(project_name)}/"
        for object_key in self._list_object_keys(prefix):
            if not object_key.startswith(prefix):
                continue
            relative_path = object_key.removeprefix(prefix)
            if self.is_project_relative_path(relative_path) and not self.is_media_relative_path(relative_path):
                target_path, _ = self._resolve_under(project_path, relative_path)
                force = False
                if target_path.is_file():
                    remote_info = self.project_file_info(project_name, relative_path)
                    remote_hash = remote_info.get("hash") if remote_info is not None else None
                    if not isinstance(remote_hash, str) or not remote_hash:
                        force = True
                    else:
                        from qiniu import etag

                        force = etag(str(target_path)) != remote_hash
                self.materialize_project_file(project_path, relative_path, force=force)

    def _delete_object_keys(self, object_keys: list[str]) -> None:
        if not object_keys:
            return

        from qiniu import BucketManager, build_batch_delete

        manager = BucketManager(self._qiniu_auth())
        try:
            for start in range(0, len(object_keys), _BATCH_DELETE_MAX_KEYS):
                object_keys_batch = object_keys[start : start + _BATCH_DELETE_MAX_KEYS]
                batch_response: Any = manager.batch(build_batch_delete(self.config.bucket, object_keys_batch))
                if not isinstance(batch_response, tuple) or len(batch_response) != 2:
                    raise MediaStorageError(f"七牛删除响应类型异常: type={type(batch_response).__name__}")
                result, info = batch_response
                sc = getattr(info, "status_code", 0)
                body = (getattr(info, "text_body", None) or "")[:400]
                # qiniu batch API: 200 = 全部成功；298 = 部分失败（response body 仍
                # 是 list，逐项 code 决定成败）；其它 status_code 才是真错误。
                if sc not in (200, 298) or not isinstance(result, list):
                    raise MediaStorageError(
                        f"七牛删除失败: status={sc} body={body} keys={object_keys_batch}"
                    )
                if len(result) != len(object_keys_batch):
                    raise MediaStorageError(
                        f"七牛删除响应数对不上: 期望 {len(object_keys_batch)} 实际 {len(result)} keys={object_keys_batch}"
                    )
                # 单项 code 检查：200 = 删除成功，612 = 对象不存在（视为成功，幂等）。
                # 其它 code 记录详细错误（key + code + data）方便定位。
                bad_items = [item for item in result
                             if not isinstance(item, dict) or item.get("code") not in {200, 612}]
                if bad_items:
                    raise MediaStorageError(
                        f"七牛删除部分失败: bad={bad_items} keys={object_keys_batch}"
                    )
        except MediaStorageError:
            raise
        except Exception as exc:
            raise MediaStorageError(f"七牛删除异常: {type(exc).__name__}: {exc}") from exc

    def delete_project_paths(self, project_name: str, relative_paths: Iterable[str | Path]) -> None:
        """精确删除项目对象；调用方应仅在成功后删除本地工作副本。"""
        if not self.enabled:
            return
        normalized_name = self._normalize_project_name(project_name)
        object_keys: list[str] = []
        for relative_path in relative_paths:
            normalized = self._normalize_relative(relative_path)
            if not self.is_project_relative_path(normalized):
                raise ValueError(f"不是受管项目路径: {relative_path}")
            object_keys.append(self.project_object_key(normalized_name, normalized))
        self._delete_object_keys(list(dict.fromkeys(object_keys)))

    def delete_global_paths(self, relative_paths: Iterable[str | Path]) -> None:
        """精确删除全局资产对象；调用方应仅在成功后删除本地副本。"""
        if not self.enabled:
            return
        object_keys = [self.global_object_key(relative_path) for relative_path in relative_paths]
        self._delete_object_keys(list(dict.fromkeys(object_keys)))

    def delete_project_media(self, project_name: str) -> None:
        """兼容旧名称：删除项目对应的全部云端对象。"""
        if not self.enabled:
            return

        normalized_name = self._normalize_project_name(project_name)
        prefix = f"{self._object_key(normalized_name)}/"
        self._delete_object_keys(self._list_object_keys(prefix))

    def delete_project(self, project_name: str) -> None:
        """删除项目对应的全部云端对象；任一批失败时调用方必须保留本地项目。"""
        self.delete_project_media(project_name)

    def materialize_project_media(self, project_path: Path) -> None:
        """将项目中缺失的受管媒体从云端物化，供导出等全量文件操作使用。"""
        project_path = Path(project_path).resolve()
        if not self.enabled:
            return
        project_name = self._normalize_project_name(project_path.name)
        prefix = f"{self._object_key(project_name)}/"
        for object_key in self._list_object_keys(prefix):
            if not object_key.startswith(prefix):
                continue
            relative_path = object_key.removeprefix(prefix)
            if self.is_media_relative_path(relative_path):
                self.materialize_project_file(project_path, relative_path)

    def _cache_index_path(self) -> Path:
        return self.data_root / _CACHE_INDEX_NAME

    def _cache_index(self) -> dict[str, Any]:
        path = self._cache_index_path()
        try:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {"entries": {}}
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), dict):
            return {"entries": {}}
        return payload

    def _save_cache_index(self, payload: dict[str, Any]) -> None:
        path = self._cache_index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
        temp_path.replace(path)

    def _record_cache_entries(self, paths: Iterable[Path]) -> None:
        entries = self._cache_index().setdefault("entries", {})
        now = time.time()
        for path in paths:
            if not path.is_file():
                continue
            resolved_path = path.resolve()
            try:
                resolved_path.relative_to(self.data_root)
            except ValueError:
                continue
            entries[str(resolved_path)] = {"accessed_at": now, "size": path.stat().st_size}
        self._save_cache_index({"entries": entries})

    def evict_local_cache(self, *, exclude: set[Path] | None = None) -> None:
        """仅淘汰模块已登记的本地缓存，不触碰尚未同步的生产文件。"""
        if not self.enabled:
            return
        excluded = {path.resolve() for path in exclude or set()}
        payload = self._cache_index()
        entries = payload["entries"]
        live: list[tuple[Path, dict[str, Any]]] = []
        for raw_path, record in list(entries.items()):
            path = Path(raw_path)
            if not path.is_file():
                entries.pop(raw_path, None)
                continue
            try:
                path.resolve().relative_to(self.data_root)
            except ValueError:
                entries.pop(raw_path, None)
                continue
            record["size"] = path.stat().st_size
            live.append((path, record))
        total_size = sum(int(record["size"]) for _, record in live)
        for path, record in sorted(live, key=lambda item: float(item[1].get("accessed_at", 0))):
            if total_size <= self.config.cache_max_bytes:
                break
            if path.resolve() in excluded:
                continue
            path.unlink(missing_ok=True)
            entries.pop(str(path.resolve()), None)
            total_size -= int(record["size"])
        self._save_cache_index(payload)


def get_media_storage(data_root: Path | None = None) -> MediaStorage:
    """按当前环境构造存储服务；不缓存，方便测试与部署时更新环境。"""
    return MediaStorage(MediaStorageConfig.from_environment(), data_root or app_data_dir())

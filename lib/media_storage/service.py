"""七牛云 Kodo 媒体存储。

项目元数据继续保存项目内相对路径。本模块只负责把受管媒体映射到确定性的
Kodo object key，并在本地路径缺失时物化一个可供现有 ffmpeg/导出代码使用的缓存。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

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
_EXCLUDED_PARTS = frozenset({".claude", "drafts", "scripts", "source"})
_CACHE_INDEX_NAME = ".media-cache-index.json"
_BATCH_DELETE_MAX_KEYS = 1000
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class MediaStorageError(RuntimeError):
    """云端媒体上传或物化失败。"""


class MediaStorageConfigurationError(MediaStorageError):
    """启用七牛存储但部署配置不完整。"""


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
    download_url_ttl_seconds: int = 900
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
            download_url_ttl_seconds=_env_positive_int("QINIU_DOWNLOAD_URL_TTL_SECONDS", 900),
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
            raise MediaStorageConfigurationError(f"启用七牛媒体存储时必须设置: {', '.join(missing)}")
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
            raise ValueError(f"非法媒体相对路径: {relative_path}")
        if ":" in path.parts[0]:
            raise ValueError(f"非法媒体相对路径: {relative_path}")
        return path.as_posix()

    @staticmethod
    def is_media_relative_path(relative_path: str | Path) -> bool:
        try:
            normalized = MediaStorage._normalize_relative(relative_path)
        except ValueError:
            return False
        path = PurePosixPath(normalized)
        return not any(part in _EXCLUDED_PARTS for part in path.parts) and path.suffix.lower() in _MEDIA_SUFFIXES

    def _resolve_under(self, root: Path, relative_path: str | Path) -> tuple[Path, str]:
        normalized = self._normalize_relative(relative_path)
        resolved_root = root.resolve()
        # Windows 对已存在的根目录和不存在的子路径可能产生不同的 extended-path
        # 表示；先从已解析根目录构造，确保后续包含关系比较使用同一种表示。
        candidate = (resolved_root / normalized).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"媒体路径越界: {relative_path}") from exc
        return candidate, normalized

    def _object_key(self, *parts: str) -> str:
        return "/".join((self.config.object_prefix, *parts))

    @staticmethod
    def _normalize_project_name(project_name: str) -> str:
        normalized = MediaStorage._normalize_relative(project_name)
        if len(PurePosixPath(normalized).parts) != 1:
            raise ValueError(f"非法项目名称: {project_name}")
        return normalized

    def project_object_key(self, project_name: str, relative_path: str | Path) -> str:
        project_name = self._normalize_project_name(project_name)
        normalized = self._normalize_relative(relative_path)
        if not self.is_media_relative_path(normalized):
            raise ValueError(f"不是受管媒体路径: {relative_path}")
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

    def signed_global_url(self, relative_path: str | Path) -> str:
        return self.signed_url_for_key(self.global_object_key(relative_path))

    def _upload_file(self, source_path: Path, object_key: str) -> None:
        """使用官方 SDK 上传，并以七牛 ETag 验证远端内容。"""
        from qiniu import etag, put_file_v2

        token = self._qiniu_auth().upload_token(
            self.config.bucket,
            object_key,
            self.config.upload_token_ttl_seconds,
            policy={"returnBody": '{"key":"$(key)","hash":"$(etag)"}'},
        )
        mime_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        result, info = put_file_v2(
            token,
            object_key,
            str(source_path),
            mime_type=mime_type,
            version="v2",
            bucket_name=self.config.bucket,
        )
        if not result or getattr(info, "status_code", 0) != 200:
            raise MediaStorageError("七牛媒体上传失败")
        if result.get("key") != object_key or result.get("hash") != etag(str(source_path)):
            raise MediaStorageError("七牛媒体上传校验失败")

    def sync_project_paths(
        self,
        project_path: Path,
        relative_paths: Iterable[str | Path],
        *,
        object_project_name: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        project_path = Path(project_path).resolve()
        object_project_name = self._normalize_project_name(object_project_name or project_path.name)
        synced_paths: list[Path] = []
        for relative_path in relative_paths:
            source_path, normalized = self._resolve_under(project_path, relative_path)
            if not self.is_media_relative_path(normalized):
                continue
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            self._upload_file(source_path, self.project_object_key(object_project_name, normalized))
            synced_paths.append(source_path)
        self._record_cache_entries(synced_paths)
        self.evict_local_cache()

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

    async def sync_global_paths_async(self, relative_paths: Iterable[str | Path]) -> None:
        await asyncio.to_thread(self.sync_global_paths, list(relative_paths))

    def materialize_project_file(self, project_path: Path, relative_path: str | Path) -> Path:
        project_path = Path(project_path).resolve()
        target_path, normalized = self._resolve_under(project_path, relative_path)
        if target_path.is_file():
            if self.enabled and self.is_media_relative_path(normalized):
                self._record_cache_entries([target_path])
            return target_path
        if not self.enabled or not self.is_media_relative_path(normalized):
            return target_path
        self._materialize(target_path, self.project_object_key(project_path.name, normalized))
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
        self._materialize(target_path, self.global_object_key(normalized))
        return target_path

    def _materialize(self, target_path: Path, object_key: str) -> None:
        key = str(target_path)
        with _LOCKS_GUARD:
            lock = _LOCKS.setdefault(key, threading.Lock())
        with lock:
            lock_path = self._object_lock_path(object_key)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with portalocker.Lock(lock_path, timeout=60):
                    if target_path.is_file():
                        return
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    temp_path: Path | None = None
                    try:
                        with tempfile.NamedTemporaryFile(dir=target_path.parent, delete=False) as temp_file:
                            temp_path = Path(temp_file.name)
                            with urlopen(self.signed_url_for_key(object_key), timeout=30) as response:
                                shutil.copyfileobj(response, temp_file)
                        if not temp_path.stat().st_size:
                            raise MediaStorageError("七牛媒体下载结果为空")
                        temp_path.replace(target_path)
                        self._record_cache_entries([target_path])
                        self.evict_local_cache(exclude={target_path})
                    finally:
                        if temp_path is not None:
                            temp_path.unlink(missing_ok=True)
            except MediaStorageError:
                raise
            except Exception as exc:
                raise MediaStorageError("七牛媒体下载失败") from exc

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
                    raise MediaStorageError("七牛媒体列表读取失败")
                items = result.get("items", [])
                if not isinstance(items, list):
                    raise MediaStorageError("七牛媒体列表响应无效")
                keys.extend(
                    item["key"] for item in items if isinstance(item, dict) and isinstance(item.get("key"), str)
                )
                if eof:
                    return keys
                marker = result.get("marker")
                if not isinstance(marker, str) or not marker:
                    raise MediaStorageError("七牛媒体列表响应缺少分页标记")
        except MediaStorageError:
            raise
        except Exception as exc:
            raise MediaStorageError("七牛媒体列表读取失败") from exc

    def delete_project_media(self, project_name: str) -> None:
        """删除项目对应的全部云端对象；任一批失败时保留本地项目供重试。"""
        if not self.enabled:
            return

        from qiniu import BucketManager, build_batch_delete

        normalized_name = self._normalize_project_name(project_name)
        prefix = f"{self._object_key(normalized_name)}/"
        object_keys = self._list_object_keys(prefix)
        if not object_keys:
            return

        manager = BucketManager(self._qiniu_auth())
        try:
            for start in range(0, len(object_keys), _BATCH_DELETE_MAX_KEYS):
                object_keys_batch = object_keys[start : start + _BATCH_DELETE_MAX_KEYS]
                # qiniu 未为 BucketManager.batch 标注返回类型；运行时仍对响应形状严格校验。
                batch_response: Any = manager.batch(build_batch_delete(self.config.bucket, object_keys_batch))
                if not isinstance(batch_response, tuple) or len(batch_response) != 2:
                    raise MediaStorageError("七牛项目媒体删除失败")
                result, info = batch_response
                if getattr(info, "status_code", 0) != 200 or not isinstance(result, list):
                    raise MediaStorageError("七牛项目媒体删除失败")
                if len(result) != len(object_keys_batch):
                    raise MediaStorageError("七牛项目媒体删除响应无效")
                # 612 表示对象已不存在；并发重复删除时目标状态已经达成，可以安全继续。
                for item in result:
                    if not isinstance(item, dict) or item.get("code") not in {200, 612}:
                        raise MediaStorageError("七牛项目媒体删除失败")
        except MediaStorageError:
            raise
        except Exception as exc:
            raise MediaStorageError("七牛项目媒体删除失败") from exc

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

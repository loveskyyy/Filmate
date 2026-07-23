"""项目媒体的对象存储与本地缓存支持。"""

from lib.media_storage.service import (
    MediaStorage,
    MediaStorageConfig,
    MediaStorageConfigurationError,
    MediaStorageError,
    get_media_storage,
)

__all__ = [
    "MediaStorage",
    "MediaStorageConfig",
    "MediaStorageConfigurationError",
    "MediaStorageError",
    "get_media_storage",
]

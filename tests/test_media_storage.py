from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from time import sleep

import pytest

import lib.media_storage.service as storage_module
from lib.media_storage import MediaStorage, MediaStorageConfig, MediaStorageConfigurationError, MediaStorageError


class _Info:
    status_code = 200


class _Auth:
    def upload_token(self, *args, **kwargs):
        return "upload-token"

    def private_download_url(self, url, *, expires):
        return f"{url}?e={expires}&token=private"


def _storage(tmp_path: Path, **overrides) -> MediaStorage:
    config = MediaStorageConfig(
        enabled=True,
        access_key="access-key",
        secret_key="secret-key",
        bucket="bucket",
        domain="https://media.example.com",
        **overrides,
    )
    storage = MediaStorage(config, tmp_path / "projects")
    storage._auth = _Auth()
    return storage


def test_disabled_config_does_not_require_credentials(monkeypatch):
    monkeypatch.delenv("QINIU_ENABLED", raising=False)
    for name in ("QINIU_ACCESS_KEY", "QINIU_SECRET_KEY", "QINIU_BUCKET", "QINIU_DOMAIN"):
        monkeypatch.delenv(name, raising=False)

    config = MediaStorageConfig.from_environment()

    assert not config.enabled


def test_enabled_config_rejects_missing_values_without_leaking_secret(monkeypatch):
    monkeypatch.setenv("QINIU_ENABLED", "true")
    monkeypatch.setenv("QINIU_ACCESS_KEY", "present")
    monkeypatch.setenv("QINIU_SECRET_KEY", "do-not-leak")
    monkeypatch.delenv("QINIU_BUCKET", raising=False)
    monkeypatch.delenv("QINIU_DOMAIN", raising=False)

    with pytest.raises(MediaStorageConfigurationError) as exc_info:
        MediaStorageConfig.from_environment()

    assert "QINIU_BUCKET" in str(exc_info.value)
    assert "do-not-leak" not in str(exc_info.value)


def test_enabled_config_rejects_http_domain_and_unsafe_prefix(monkeypatch):
    monkeypatch.setenv("QINIU_ENABLED", "true")
    monkeypatch.setenv("QINIU_ACCESS_KEY", "access-key")
    monkeypatch.setenv("QINIU_SECRET_KEY", "secret-key")
    monkeypatch.setenv("QINIU_BUCKET", "bucket")
    monkeypatch.setenv("QINIU_DOMAIN", "http://media.example.com")
    monkeypatch.setenv("QINIU_OBJECT_PREFIX", "projects")

    with pytest.raises(MediaStorageConfigurationError, match="HTTPS"):
        MediaStorageConfig.from_environment()

    monkeypatch.setenv("QINIU_DOMAIN", "https://media.example.com")
    monkeypatch.setenv("QINIU_OBJECT_PREFIX", "../projects")
    with pytest.raises(MediaStorageConfigurationError, match="OBJECT_PREFIX"):
        MediaStorageConfig.from_environment()


def test_object_key_and_path_whitelist(tmp_path):
    storage = _storage(tmp_path)

    assert storage.project_object_key("demo", "videos/scene_01.mp4") == "projects/demo/videos/scene_01.mp4"
    assert (
        storage.global_object_key("_global_assets/character/Alice.png") == "projects/_global_assets/character/Alice.png"
    )
    assert not storage.is_media_relative_path("source/chapter.txt")
    assert not storage.is_media_relative_path("scripts/episode_1.json")
    with pytest.raises(ValueError):
        storage.project_object_key("demo", "../outside.mp4")
    with pytest.raises(ValueError):
        storage.project_object_key("demo/other", "videos/scene_01.mp4")


def test_sync_uses_v2_upload_and_verifies_etag(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    media_path = tmp_path / "projects" / "demo" / "videos" / "scene_01.mp4"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"video")
    captured = {}

    def put_file_v2(token, key, file_path, **kwargs):
        captured.update(token=token, key=key, file_path=file_path, **kwargs)
        return {"key": key, "hash": "local-etag"}, _Info()

    monkeypatch.setattr("qiniu.put_file_v2", put_file_v2)
    monkeypatch.setattr("qiniu.etag", lambda _: "local-etag")

    storage.sync_project_paths(media_path.parents[1], ["videos/scene_01.mp4"])

    assert captured["key"] == "projects/demo/videos/scene_01.mp4"
    assert captured["version"] == "v2"
    assert captured["bucket_name"] == "bucket"


def test_sync_project_media_uses_final_project_name_for_staging_dir(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    staging_dir = tmp_path / "staging" / "project"
    (staging_dir / "videos").mkdir(parents=True)
    (staging_dir / "scripts").mkdir()
    (staging_dir / "videos" / "scene_01.mp4").write_bytes(b"video")
    (staging_dir / "storyboards").mkdir()
    (staging_dir / "storyboards" / "scene_01.png").write_bytes(b"image")
    (staging_dir / "scripts" / "episode_1.json").write_text("{}", encoding="utf-8")

    uploaded: list[str] = []
    monkeypatch.setattr(storage, "_upload_file", lambda _path, key: uploaded.append(key))

    storage.sync_project_media(staging_dir, object_project_name="imported-demo")

    assert uploaded == [
        "projects/imported-demo/storyboards/scene_01.png",
        "projects/imported-demo/videos/scene_01.mp4",
    ]
    assert storage._cache_index()["entries"] == {}


def test_sync_rejects_etag_mismatch(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    media_path = tmp_path / "projects" / "demo" / "videos" / "scene_01.mp4"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"video")

    monkeypatch.setattr("qiniu.put_file_v2", lambda *args, **kwargs: ({"key": args[1], "hash": "wrong"}, _Info()))
    monkeypatch.setattr("qiniu.etag", lambda _: "local-etag")

    with pytest.raises(MediaStorageError, match="上传校验失败"):
        storage.sync_project_paths(media_path.parents[1], ["videos/scene_01.mp4"])


def test_private_signed_url_uses_configured_expiry(tmp_path):
    storage = _storage(tmp_path, download_url_ttl_seconds=321)

    url = storage.signed_project_url("demo", "videos/scene_01.mp4")

    assert url == "https://media.example.com/projects/demo/videos/scene_01.mp4?e=321&token=private"


def test_materialization_is_object_locked_and_downloaded_once(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    calls = 0

    def download(*args, **kwargs):
        nonlocal calls
        calls += 1
        sleep(0.05)
        return BytesIO(b"remote-video")

    monkeypatch.setattr(storage_module, "urlopen", download)
    project_path = tmp_path / "projects" / "demo"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: storage.materialize_project_file(project_path, "videos/scene_01.mp4"),
                range(2),
            )
        )

    assert calls == 1
    assert results[0] == results[1]
    assert results[0].read_bytes() == b"remote-video"


def test_export_materialization_lists_project_prefix(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    listed = []

    class _BucketManager:
        def __init__(self, auth):
            assert isinstance(auth, _Auth)

        def list(self, bucket, prefix, marker, limit, delimiter):
            listed.append((bucket, prefix, marker, limit, delimiter))
            return (
                {"items": [{"key": "projects/demo/videos/scene_01.mp4"}, {"key": "projects/demo/project.json"}]},
                True,
                _Info(),
            )

    monkeypatch.setattr("qiniu.BucketManager", _BucketManager)
    monkeypatch.setattr(storage_module, "urlopen", lambda *args, **kwargs: BytesIO(b"remote-video"))

    project_path = tmp_path / "projects" / "demo"
    storage.materialize_project_media(project_path)

    assert listed == [("bucket", "projects/demo/", None, 1000, None)]
    assert (project_path / "videos" / "scene_01.mp4").read_bytes() == b"remote-video"
    assert not (project_path / "project.json").exists()


def test_delete_project_media_deletes_all_listed_objects(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    deleted_batches: list[list[str]] = []
    listed_prefixes: list[str] = []

    class _BucketManager:
        def __init__(self, auth):
            assert isinstance(auth, _Auth)

        def batch(self, operations):
            deleted_batches.append(operations)
            return [{"code": 200} for _ in operations], _Info()

    def _list_object_keys(prefix: str) -> list[str]:
        listed_prefixes.append(prefix)
        return [f"{prefix}videos/scene_{index:04d}.mp4" for index in range(1001)]

    monkeypatch.setattr(storage, "_list_object_keys", _list_object_keys)
    monkeypatch.setattr("qiniu.BucketManager", _BucketManager)

    storage.delete_project_media("demo")

    assert listed_prefixes == ["projects/demo/"]
    assert [len(batch) for batch in deleted_batches] == [1000, 1]
    assert all(operation.startswith("delete/") for batch in deleted_batches for operation in batch)


def test_delete_project_media_rejects_partial_batch_failure(tmp_path, monkeypatch):
    storage = _storage(tmp_path)

    class _BucketManager:
        def __init__(self, _auth):
            pass

        def batch(self, _operations):
            return [{"code": 200}, {"code": 631}], _Info()

    monkeypatch.setattr(
        storage,
        "_list_object_keys",
        lambda prefix: [
            f"{prefix}videos/scene_01.mp4",
            f"{prefix}thumbnails/scene_01.jpg",
        ],
    )
    monkeypatch.setattr("qiniu.BucketManager", _BucketManager)

    with pytest.raises(MediaStorageError, match="删除失败"):
        storage.delete_project_media("demo")

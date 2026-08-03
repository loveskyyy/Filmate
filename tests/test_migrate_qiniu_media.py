from __future__ import annotations

from scripts import migrate_qiniu_media


class _Storage:
    def __init__(self):
        self.project_syncs: list[tuple[str, list[str]]] = []
        self.global_syncs: list[list[str]] = []
        self.project_hashes: dict[tuple[str, str], str] = {}
        self.global_hashes: dict[str, str] = {}

    @staticmethod
    def is_media_relative_path(path: str) -> bool:
        return path.endswith((".png", ".mp4"))

    @staticmethod
    def is_project_relative_path(path: str) -> bool:
        return not any(part.startswith(".") for part in path.split("/"))

    def sync_project_paths(self, project_path, relative_paths, **_kwargs):
        paths = list(relative_paths)
        self.project_syncs.append((project_path.name, paths))
        for relative in paths:
            self.project_hashes[(project_path.name, relative)] = migrate_qiniu_media._file_etag(project_path / relative)

    def sync_global_paths(self, relative_paths):
        paths = list(relative_paths)
        self.global_syncs.append(paths)

    def project_file_info(self, project_name, relative_path):
        hash_value = self.project_hashes.get((project_name, relative_path))
        return {"hash": hash_value} if hash_value else None

    def global_file_info(self, relative_path):
        hash_value = self.global_hashes.get(relative_path)
        return {"hash": hash_value} if hash_value else None

    @staticmethod
    def project_object_key(project_name, relative_path):
        if "/" in project_name or "\\" in project_name or project_name in {".", ".."}:
            raise ValueError("非法项目名称")
        return f"projects/{project_name}/{relative_path}"


def test_project_migration_is_dry_run_then_resumes_from_checkpoint(tmp_path):
    project_path = tmp_path / "demo"
    video = project_path / "videos" / "scene_01.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    project_file = project_path / "project.json"
    project_file.write_text("{}", encoding="utf-8")
    storage = _Storage()
    checkpoint_dir = tmp_path / ".qiniu-migrations"

    dry_run = migrate_qiniu_media._migrate_project(
        project_path,
        storage=storage,
        apply=False,
        delete_local=False,
        checkpoint_dir=checkpoint_dir,
    )
    applied = migrate_qiniu_media._migrate_project(
        project_path,
        storage=storage,
        apply=True,
        delete_local=False,
        checkpoint_dir=checkpoint_dir,
    )
    resumed = migrate_qiniu_media._migrate_project(
        project_path,
        storage=storage,
        apply=True,
        delete_local=False,
        checkpoint_dir=checkpoint_dir,
    )

    assert dry_run == {"project": "demo", "discovered": 2, "uploaded": 0, "checkpointed": 0}
    assert applied == {"project": "demo", "discovered": 2, "uploaded": 2, "checkpointed": 0}
    assert resumed == {"project": "demo", "discovered": 2, "uploaded": 0, "checkpointed": 2}
    assert storage.project_syncs == [("demo", ["project.json"]), ("demo", ["videos/scene_01.mp4"])]
    assert video.exists()
    assert project_file.exists()


def test_project_migration_reuploads_file_changed_after_checkpoint(tmp_path):
    project_path = tmp_path / "demo"
    project_path.mkdir()
    project_file = project_path / "project.json"
    project_file.write_text('{"title":"v1"}', encoding="utf-8")
    storage = _Storage()
    checkpoint_dir = tmp_path / ".qiniu-migrations"

    migrate_qiniu_media._migrate_project(
        project_path,
        storage=storage,
        apply=True,
        delete_local=False,
        checkpoint_dir=checkpoint_dir,
    )
    project_file.write_text('{"title":"v2"}', encoding="utf-8")
    resumed = migrate_qiniu_media._migrate_project(
        project_path,
        storage=storage,
        apply=True,
        delete_local=False,
        checkpoint_dir=checkpoint_dir,
    )

    assert resumed["uploaded"] == 1
    assert storage.project_syncs == [("demo", ["project.json"]), ("demo", ["project.json"])]


def test_project_migration_rejects_path_like_project_name_before_scan(tmp_path):
    storage = _Storage()

    try:
        migrate_qiniu_media._migrate_project(
            tmp_path / "..",
            storage=storage,
            apply=False,
            delete_local=False,
            checkpoint_dir=tmp_path / ".qiniu-migrations",
        )
    except ValueError as exc:
        assert "非法项目名称" in str(exc)
    else:
        raise AssertionError("path-like project name must be rejected")


def test_project_migration_delete_local_keeps_non_media_working_copy(tmp_path):
    project_path = tmp_path / "demo"
    video = project_path / "videos" / "scene_01.mp4"
    source = project_path / "source" / "chapter.txt"
    video.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    source.write_text("chapter", encoding="utf-8")

    migrate_qiniu_media._migrate_project(
        project_path,
        storage=_Storage(),
        apply=True,
        delete_local=True,
        checkpoint_dir=tmp_path / ".qiniu-migrations",
    )

    assert not video.exists()
    assert source.exists()


def test_global_asset_migration_uses_global_storage_namespace(tmp_path):
    image = tmp_path / "_global_assets" / "scene" / "scene.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    storage = _Storage()

    result = migrate_qiniu_media._migrate_global_assets(
        tmp_path,
        storage=storage,
        apply=True,
        delete_local=False,
        checkpoint_dir=tmp_path / ".qiniu-migrations",
    )

    assert result == {"project": "_global_assets", "discovered": 1, "uploaded": 1, "checkpointed": 0}
    assert storage.global_syncs == [["_global_assets/scene/scene.png"]]

from __future__ import annotations

from scripts import migrate_qiniu_media


class _Storage:
    def __init__(self):
        self.project_syncs: list[tuple[str, list[str]]] = []
        self.global_syncs: list[list[str]] = []

    @staticmethod
    def is_media_relative_path(path: str) -> bool:
        return path.endswith((".png", ".mp4"))

    def sync_project_paths(self, project_path, relative_paths):
        self.project_syncs.append((project_path.name, list(relative_paths)))

    def sync_global_paths(self, relative_paths):
        self.global_syncs.append(list(relative_paths))


def test_project_migration_is_dry_run_then_resumes_from_checkpoint(tmp_path):
    project_path = tmp_path / "demo"
    video = project_path / "videos" / "scene_01.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
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

    assert dry_run == {"project": "demo", "discovered": 1, "uploaded": 0, "checkpointed": 0}
    assert applied == {"project": "demo", "discovered": 1, "uploaded": 1, "checkpointed": 0}
    assert resumed == {"project": "demo", "discovered": 1, "uploaded": 0, "checkpointed": 1}
    assert storage.project_syncs == [("demo", ["videos/scene_01.mp4"])]
    assert video.exists()


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

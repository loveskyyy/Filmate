import json
from pathlib import Path

from lib import project_manager as project_manager_module
from lib.project_manager import ProjectManager


class _CloudStorage:
    enabled = True

    def __init__(self):
        self.synced: list[tuple[str, tuple[str, ...]]] = []

    def list_project_names(self) -> list[str]:
        return ["cloud-demo"]

    def project_file_exists(self, project_name: str, relative_path: str) -> bool:
        return project_name == "cloud-demo" and relative_path == "project.json"

    def materialize_project_data(self, project_dir: Path) -> None:
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "scripts").mkdir(exist_ok=True)
        (project_dir / "project.json").write_text(
            json.dumps({"title": "Cloud Demo", "content_mode": "narration"}),
            encoding="utf-8",
        )
        (project_dir / "scripts" / "episode_1.json").write_text(
            json.dumps({"content_mode": "narration", "segments": []}),
            encoding="utf-8",
        )

    def materialize_project_file(self, project_dir: Path, relative_path: str) -> Path:
        return project_dir / relative_path

    def sync_project_paths(self, project_dir: Path, relative_paths) -> None:
        paths = tuple(str(path) for path in relative_paths)
        assert all((project_dir / path).is_file() for path in paths)
        self.synced.append((project_dir.name, paths))

    def sync_project_files(self, project_dir: Path, **_kwargs) -> None:
        relative_paths = [
            path.relative_to(project_dir).as_posix()
            for path in project_dir.rglob("*")
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(project_dir).parts)
        ]
        self.sync_project_paths(project_dir, relative_paths)


class _LocalProjectCloudStorage(_CloudStorage):
    def list_project_names(self) -> list[str]:
        return []

    def project_file_exists(self, project_name: str, relative_path: str) -> bool:
        return False

    def materialize_project_data(self, project_dir: Path) -> None:
        raise AssertionError("本地项目首次上传前不应从空远端恢复")


def test_project_manager_discovers_restores_and_syncs_cloud_project(tmp_path, monkeypatch):
    storage = _CloudStorage()
    monkeypatch.setattr(project_manager_module, "get_media_storage", lambda _root: storage, raising=False)
    pm = ProjectManager(tmp_path / "projects")

    assert pm.list_projects() == ["cloud-demo"]
    assert pm.load_project("cloud-demo")["title"] == "Cloud Demo"
    assert pm.load_script("cloud-demo", "episode_1.json")["segments"] == []

    project = pm.load_project("cloud-demo")
    project["title"] = "Updated"
    pm.save_project("cloud-demo", project)
    pm.save_script(
        "cloud-demo",
        {"content_mode": "narration", "segments": []},
        "episode_1.json",
        validate=False,
    )

    assert ("cloud-demo", ("project.json",)) in storage.synced
    assert ("cloud-demo", ("scripts/episode_1.json",)) in storage.synced


def test_remote_project_without_registered_owner_is_hidden(tmp_path, monkeypatch):
    storage = _CloudStorage()
    monkeypatch.setattr(project_manager_module, "get_media_storage", lambda _root: storage, raising=False)
    pm = ProjectManager(tmp_path / "projects")

    assert pm.list_projects(user_id=1) == []
    pm.get_project_path("cloud-demo")
    assert pm.list_projects(user_id=1) == []
    pm._project_owners_path.write_text(
        json.dumps({"schema_version": 1, "owners": {"cloud-demo": 2}}),
        encoding="utf-8",
    )

    assert pm.list_projects(user_id=2) == ["cloud-demo"]
    assert pm.is_project_owned_by("cloud-demo", 1) is False
    assert pm.is_project_owned_by("cloud-demo", 2) is True


def test_local_project_is_uploaded_on_first_cloud_activation(tmp_path, monkeypatch):
    projects_root = tmp_path / "projects"
    project_dir = projects_root / "local-demo"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        json.dumps({"schema_version": 3, "title": "Local Demo", "content_mode": "narration"}),
        encoding="utf-8",
    )
    storage = _LocalProjectCloudStorage()
    monkeypatch.setattr(project_manager_module, "get_media_storage", lambda _root: storage, raising=False)

    pm = ProjectManager(projects_root)

    assert pm.get_project_path("local-demo") == project_dir
    assert ("local-demo", ("project.json",)) in storage.synced

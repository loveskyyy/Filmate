"""项目与全局资产的用户隔离行为测试。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.project_manager import ProjectManager
from server.auth import CurrentUser, CurrentUserInfo, create_token, get_current_user
from server.routers import files, projects
from server.services.project_archive import ProjectArchiveService, ProjectArchiveValidationError


def test_project_manager_lists_only_projects_owned_by_user(tmp_path: Path) -> None:
    manager = ProjectManager(tmp_path / "projects")

    manager.create_project("alice-project", user_id=2)
    manager.create_project("bob-project", user_id=3)

    assert manager.list_projects(user_id=2) == ["alice-project"]
    assert manager.list_projects(user_id=3) == ["bob-project"]
    assert manager.is_project_owned_by("alice-project", 2) is True
    assert manager.is_project_owned_by("alice-project", 3) is False


def test_legacy_project_without_owner_record_belongs_to_default_user(tmp_path: Path) -> None:
    manager = ProjectManager(tmp_path / "projects")
    legacy_dir = manager.projects_root / "legacy-project"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "project.json").write_text('{"name":"legacy-project"}', encoding="utf-8")

    assert manager.list_projects(user_id=1) == ["legacy-project"]
    assert manager.list_projects(user_id=2) == []


class _StatusCalculator:
    def calculate_project_status(self, name, project, *, preloaded_scripts=None):
        return {}


def test_projects_api_lists_and_creates_in_current_user_scope(tmp_path: Path, monkeypatch) -> None:
    manager = ProjectManager(tmp_path / "projects")
    manager.create_project("alice-project", user_id=2)
    manager.create_project("bob-project", user_id=3)
    current_user = CurrentUserInfo(id=2, sub="alice", role="user")

    monkeypatch.setattr(projects, "get_project_manager", lambda: manager)
    monkeypatch.setattr(projects, "get_status_calculator", lambda: _StatusCalculator())
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.include_router(projects.router, prefix="/api/v1")

    with TestClient(app) as client:
        response = client.get("/api/v1/projects")
        assert response.status_code == 200
        assert [item["name"] for item in response.json()["projects"]] == ["alice-project"]

        created = client.post(
            "/api/v1/projects",
            json={"name": "alice-new", "title": "Alice", "content_mode": "narration"},
        )
        assert created.status_code == 200, created.text

    assert manager.is_project_owned_by("alice-new", 2) is True
    assert manager.is_project_owned_by("alice-new", 3) is False


def test_authenticated_project_route_hides_another_users_project(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-key-that-is-at-least-32-bytes")
    manager = ProjectManager(data_dir)
    manager.create_project("alice-project", user_id=2)

    app = FastAPI()

    @app.get("/projects/{project_name}")
    async def read_project(project_name: str, _user: CurrentUser):
        return {"project_name": project_name}

    with TestClient(app) as client:
        alice_token = create_token("alice", user_id=2, role="user")
        bob_token = create_token("bob", user_id=3, role="user")
        alice = client.get("/projects/alice-project", headers={"Authorization": f"Bearer {alice_token}"})
        bob = client.get("/projects/alice-project", headers={"Authorization": f"Bearer {bob_token}"})

    assert alice.status_code == 200
    assert bob.status_code == 404


def test_disabled_auth_still_limits_requests_to_default_user(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    manager = ProjectManager(data_dir)
    manager.create_project("other-project", user_id=2)

    app = FastAPI()

    @app.get("/projects/{project_name}")
    async def read_project(project_name: str, _user: CurrentUser):
        return {"project_name": project_name}

    with TestClient(app) as client:
        response = client.get("/projects/other-project")

    assert response.status_code == 404


async def test_skill_enqueue_uses_project_owner_when_user_is_not_explicit(tmp_path: Path, monkeypatch) -> None:
    from lib import generation_queue_client

    data_dir = tmp_path / "data"
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_dir))
    manager = ProjectManager(data_dir)
    manager.create_project("alice-project", user_id=2)
    captured: dict[str, object] = {}

    class _Queue:
        async def is_worker_online(self, *, name: str) -> bool:
            return True

        async def enqueue_task(self, **kwargs):
            captured.update(kwargs)
            return {"task_id": "task-1", "deduped": False}

    monkeypatch.setattr(generation_queue_client, "get_generation_queue", lambda: _Queue())
    await generation_queue_client.enqueue_task_only(
        project_name="alice-project",
        task_type="character",
        media_type="image",
        resource_id="Alice",
    )

    assert captured["user_id"] == 2


def test_global_asset_file_is_visible_only_to_owning_user(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-key-that-is-at-least-32-bytes")
    manager = ProjectManager(data_dir)
    image_path = manager.get_global_assets_root(user_id=2) / "character" / "alice.png"
    image_path.write_bytes(b"alice-image")
    monkeypatch.setattr(files, "get_project_manager", lambda: manager)

    app = FastAPI()
    app.include_router(files.router, prefix="/api/v1")

    with TestClient(app) as client:
        alice_token = create_token("alice", user_id=2, role="user")
        bob_token = create_token("bob", user_id=3, role="user")
        alice = client.get(f"/api/v1/global-assets/2/character/alice.png?token={alice_token}")
        bob = client.get(f"/api/v1/global-assets/2/character/alice.png?token={bob_token}")

    assert alice.status_code == 200
    assert alice.content == b"alice-image"
    assert bob.status_code == 404


def test_imported_project_is_assigned_to_importing_user(tmp_path: Path) -> None:
    manager = ProjectManager(tmp_path / "projects")
    manager.create_project("imported-project")
    manager.create_project_metadata("imported-project", "Imported", "Anime", "narration")
    service = ProjectArchiveService(manager)
    archive_path, _ = service.export_project("imported-project")
    shutil.rmtree(manager.get_project_path("imported-project"))
    manager.remove_project_owner("imported-project")

    result = service.import_project_archive(archive_path, user_id=2)

    assert manager.get_project_owner(result.project_name) == 2


def test_import_cannot_overwrite_another_users_project(tmp_path: Path) -> None:
    manager = ProjectManager(tmp_path / "projects")
    manager.create_project("shared-name", user_id=3)
    manager.create_project_metadata("shared-name", "Shared", "Anime", "narration")
    service = ProjectArchiveService(manager)
    archive_path, _ = service.export_project("shared-name")

    try:
        service.import_project_archive(archive_path, conflict_policy="overwrite", user_id=2)
    except ProjectArchiveValidationError as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("不应允许覆盖其他用户的同名项目")

"""End-to-end test for the project flow with the 404 -> FileNotFoundError fix.

Scenarios:
  1. Create project -> save_script -> verify uploaded to Qiniu
  2. Delete local script file -> load_script -> restores from Qiniu
  3. load_script for a non-existent script (no local, no Qiniu)
     -> MUST raise FileNotFoundError, MUST NOT raise MediaStorageError
  4. MediaStorageNotFoundError: materialize_project_file on a path that only exists in Qiniu
  5. Round-trip: script content equality (write -> delete local -> load)
"""

# Standalone script — disable pytest auto-collection. Run with: python tests/test_project_flow.py
__test__ = False
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from lib.app_data_dir import app_data_dir
from lib.media_storage import (
    MediaStorage,
    MediaStorageError,
    MediaStorageNotFoundError,
    get_media_storage,
)
from lib.project_manager import ProjectManager
from lib.db import async_session_factory
from sqlalchemy import select
from lib.db.models.user import User


PASS: list[str] = []
FAIL: list[str] = []


def chk(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name} {detail}")
    else:
        FAIL.append(f"{name} {detail}")
        print(f"  [FAIL] {name} {detail}")


PROJECT_NAME = f"e2e-{uuid.uuid4().hex[:8]}"  # matches ^[A-Za-z0-9-]+$
SCRIPT_FILENAME = "chapter_01_script.json"
SCRIPT_PAYLOAD = {
    "metadata": {
        "episode": 1,
        "title": "Episode 1 test",
        "created_at": "2026-08-04T00:00:00Z",
        "status": "draft",
        "total_scenes": 1,
        "estimated_duration_seconds": 8,
    },
    "novel": {"chapter": "chapter_01"},
    "characters": {},
    "scenes": [
        {
            "id": "scene_1",
            "title": "opening",
            "duration_seconds": 8,
            "shots": [],
        }
    ],
}


async def main() -> int:
    print("=== Project flow E2E test ===\n")
    pm = ProjectManager()
    storage = get_media_storage(app_data_dir())
    print(f"  test project : {PROJECT_NAME}")
    print(f"  storage      : enabled={storage.enabled} bucket={storage.config.bucket!r} prefix={storage.config.object_prefix!r}")
    print()

    # 0) Ensure the test user exists (default user_id=1 is created on startup)
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.id == 1))
        u = r.scalar_one_or_none()
        chk("0.user_exists", u is not None)

    # 1) Create project + save script
    print("[1] create project + save_script (uploads to Qiniu)")
    try:
        pm.create_project(PROJECT_NAME, content_mode="narration")
        chk("1.create_project", True)
    except Exception as e:  # noqa: BLE001
        chk("1.create_project", False, f"{type(e).__name__}: {e}")
        return 1

    try:
        saved = pm.save_script(PROJECT_NAME, SCRIPT_PAYLOAD, SCRIPT_FILENAME, validate=False)
        chk("1.save_script", saved.exists() and saved.is_file(),
            f"-> {saved}")
    except Exception as e:  # noqa: BLE001
        chk("1.save_script", False, f"{type(e).__name__}: {e}")
        return 1

    # 1b) Verify the script object exists in Qiniu
    expected_key = storage.project_object_key(PROJECT_NAME, f"scripts/{SCRIPT_FILENAME}")
    from qiniu import BucketManager
    manager = BucketManager(storage._qiniu_auth())
    result, eof, info = manager.list(storage.config.bucket, expected_key.rsplit("/", 1)[0] + "/", None, 100, None)
    listed = [it["key"] for it in (result or {}).get("items", []) if isinstance(it, dict)]
    chk("1.qiniu_has_script", expected_key in listed,
        f"key={expected_key!r}  listed={listed}")

    # 2) Delete local script; load_script should restore it from Qiniu
    print("\n[2] delete local script -> load_script restores from Qiniu")
    saved.unlink()
    chk("2.local_removed", not saved.exists())
    try:
        loaded = pm.load_script(PROJECT_NAME, SCRIPT_FILENAME)
        chk("2.load_after_restore", loaded["metadata"]["title"] == SCRIPT_PAYLOAD["metadata"]["title"],
            f"got title={loaded.get('metadata', {}).get('title')!r}")
        chk("2.local_restored", saved.exists(),
            f"local file should be re-materialized at {saved}")
    except Exception as e:  # noqa: BLE001
        chk("2.load_after_restore", False, f"{type(e).__name__}: {e}")

    # 3) load_script for a script that does NOT exist anywhere
    print("\n[3] load_script for non-existent script -> FileNotFoundError (NOT MediaStorageError)")
    missing_filename = f"never_existed_{uuid.uuid4().hex[:6]}.json"
    try:
        pm.load_script(PROJECT_NAME, missing_filename)
        chk("3.raise", False, "expected FileNotFoundError, got nothing")
    except FileNotFoundError as e:
        chk("3.raise", True, f"FileNotFoundError: {e}")
    except MediaStorageError as e:  # noqa: BLE001
        chk("3.raise", False, f"got MediaStorageError (should be FileNotFoundError): {e}")
    except Exception as e:  # noqa: BLE001
        chk("3.raise", False, f"wrong exception type: {type(e).__name__}: {e}")

    # 4) Direct materialize_project_file on a path that does not exist in Qiniu
    print("\n[4] materialize_project_file on missing key -> MediaStorageNotFoundError (subclass of MediaStorageError)")
    missing_rel = f"scripts/never_uploaded_{uuid.uuid4().hex[:6]}.json"
    try:
        storage.materialize_project_file(pm.get_project_path(PROJECT_NAME), missing_rel)
        chk("4.raise", False, "expected MediaStorageNotFoundError, got nothing")
    except MediaStorageNotFoundError as e:
        chk("4.raise_not_found", True, f"MediaStorageNotFoundError: {e}")
        chk("4.is_subclass", issubclass(MediaStorageNotFoundError, MediaStorageError), "")
    except MediaStorageError as e:  # noqa: BLE001
        chk("4.raise_not_found", False, f"got MediaStorageError (not the specific NotFound): {e}")
    except Exception as e:  # noqa: BLE001
        chk("4.raise_not_found", False, f"wrong exception type: {type(e).__name__}: {e}")

    # 5) Round-trip content equality
    print("\n[5] content round-trip: write -> delete local -> read -> same business fields")
    expected = SCRIPT_PAYLOAD
    saved2 = pm.save_script(PROJECT_NAME, expected, SCRIPT_FILENAME, validate=False)
    saved2.unlink()
    reloaded = pm.load_script(PROJECT_NAME, SCRIPT_FILENAME)
    # save_script refreshes metadata.updated_at on every write, so compare business fields
    # only (not the volatile metadata.updated_at).
    chk("5.title_preserved", reloaded.get("metadata", {}).get("title") == expected["metadata"]["title"],
        f"got {reloaded.get('metadata', {}).get('title')!r}")
    chk("5.chapter_preserved", reloaded.get("novel", {}).get("chapter") == expected["novel"]["chapter"])
    chk("5.scenes_count", len(reloaded.get("scenes", [])) == len(expected["scenes"]),
        f"got {len(reloaded.get('scenes', []))} scenes")
    chk("5.scene1_id", reloaded["scenes"][0]["id"] == expected["scenes"][0]["id"],
        f"got {reloaded['scenes'][0]['id']!r}")
    chk("5.scene1_duration", reloaded["scenes"][0]["duration_seconds"] == expected["scenes"][0]["duration_seconds"])

    # 6) version_manager._load_versions on a fresh project (no versions.json in Qiniu)
    #    -> must return empty dict, NOT raise MediaStorageNotFoundError.
    print("\n[6] version_manager._load_versions on fresh project -> empty dict, no exception")
    from lib.version_manager import VersionManager
    proj_dir = pm.get_project_path(PROJECT_NAME)
    vm = VersionManager(proj_dir)
    # Manually delete any local versions.json (if it exists) so we exercise the missing path
    versions_file = proj_dir / "versions" / "versions.json"
    if versions_file.exists():
        versions_file.unlink()
    try:
        data = vm._load_versions()
        chk("6.returns_dict", isinstance(data, dict), f"got {type(data).__name__}")
        # Must be empty per resource type
        empty = all(not v for v in data.values())
        chk("6.empty_per_resource", empty, f"got {data!r}")
    except Exception as e:  # noqa: BLE001
        chk("6.returns_dict", False, f"raised {type(e).__name__}: {e}")
        chk("6.empty_per_resource", False, "skipped because previous check failed")

    # 6b) grid_manager.get() on a missing grid -> None (not exception)
    print("\n[6b] grid_manager.get() on missing grid -> None, no exception")
    try:
        from lib.grid_manager import GridManager
        gm = GridManager(proj_dir)
        result = gm.get("never-existed-grid-id")
        chk("6b.returns_none", result is None, f"got {result!r}")
    except Exception as e:  # noqa: BLE001
        chk("6b.returns_none", False, f"raised {type(e).__name__}: {e}")

    # Cleanup
    print("\n[cleanup] delete remote objects + local test project")
    try:
        storage.delete_project_media(PROJECT_NAME)
        chk("cleanup.qiniu_deleted", True)
    except Exception as e:  # noqa: BLE001
        chk("cleanup.qiniu_deleted", False, f"{e}")
    proj_dir = pm.get_project_path(PROJECT_NAME)
    if proj_dir.exists():
        shutil.rmtree(proj_dir, ignore_errors=True)
    chk("cleanup.local_removed", not proj_dir.exists())

    print(f"\n=== RESULT: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        print("Failures:")
        for f in FAIL:
            print(f"  - {f}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

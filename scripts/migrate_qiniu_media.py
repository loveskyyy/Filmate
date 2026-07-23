"""分批将本地项目媒体迁移到七牛 Kodo。

默认仅输出 dry-run 报告。传入 ``--apply`` 才会上传；``--delete-local`` 还需
显式与 ``--apply`` 联用，并且仅在单个文件上传校验成功后删除本地副本。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.app_data_dir import app_data_dir
from lib.media_storage import MediaStorageError, get_media_storage


def _iter_project_media(project_path: Path, storage) -> list[str]:
    paths: list[str] = []
    for path in sorted(project_path.rglob("*")):
        if path.is_file():
            relative = path.relative_to(project_path).as_posix()
            if storage.is_media_relative_path(relative):
                paths.append(relative)
    return paths


def _iter_global_media(data_root: Path, storage) -> list[str]:
    global_root = data_root / "_global_assets"
    if not global_root.is_dir():
        return []
    paths: list[str] = []
    for path in sorted(global_root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(data_root).as_posix()
            if storage.is_media_relative_path(relative):
                paths.append(relative)
    return paths


def _load_checkpoint(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return set()
    completed = payload.get("completed") if isinstance(payload, dict) else None
    return {item for item in completed if isinstance(item, str)} if isinstance(completed, list) else set()


def _save_checkpoint(path: Path, completed: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"completed": sorted(completed)}, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _migrate_project(
    project_path: Path, *, storage, apply: bool, delete_local: bool, checkpoint_dir: Path
) -> dict[str, int | str]:
    media_paths = _iter_project_media(project_path, storage)
    checkpoint = checkpoint_dir / f"{project_path.name}.json"
    completed = _load_checkpoint(checkpoint)
    uploaded = 0
    skipped = 0
    for relative in media_paths:
        if relative in completed:
            skipped += 1
            continue
        if not apply:
            continue
        storage.sync_project_paths(project_path, [relative])
        completed.add(relative)
        _save_checkpoint(checkpoint, completed)
        uploaded += 1
        if delete_local:
            (project_path / relative).unlink(missing_ok=True)
    return {
        "project": project_path.name,
        "discovered": len(media_paths),
        "uploaded": uploaded,
        "checkpointed": skipped,
    }


def _migrate_global_assets(
    data_root: Path,
    *,
    storage,
    apply: bool,
    delete_local: bool,
    checkpoint_dir: Path,
) -> dict[str, int | str]:
    media_paths = _iter_global_media(data_root, storage)
    checkpoint = checkpoint_dir / "_global_assets.json"
    completed = _load_checkpoint(checkpoint)
    uploaded = 0
    skipped = 0
    for relative in media_paths:
        if relative in completed:
            skipped += 1
            continue
        if not apply:
            continue
        storage.sync_global_paths([relative])
        completed.add(relative)
        _save_checkpoint(checkpoint, completed)
        uploaded += 1
        if delete_local:
            (data_root / relative).unlink(missing_ok=True)
    return {
        "project": "_global_assets",
        "discovered": len(media_paths),
        "uploaded": uploaded,
        "checkpointed": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移 ArcReel 项目媒体到七牛 Kodo")
    parser.add_argument("--project", action="append", dest="projects", help="仅迁移指定项目，可重复传入")
    parser.add_argument("--apply", action="store_true", help="执行上传；未传时仅 dry-run")
    parser.add_argument("--delete-local", action="store_true", help="上传校验成功后删除本地媒体缓存")
    args = parser.parse_args()
    if args.delete_local and not args.apply:
        parser.error("--delete-local 必须与 --apply 一起使用")

    data_root = app_data_dir()
    storage = get_media_storage(data_root)
    if not storage.enabled:
        raise MediaStorageError("请先设置 QINIU_ENABLED=true 和完整的七牛环境变量")

    project_names = args.projects or [
        child.name
        for child in data_root.iterdir()
        if child.is_dir() and not child.name.startswith("_") and not child.name.startswith(".")
    ]
    checkpoint_dir = data_root / ".qiniu-migrations"
    reports = []
    if not args.projects:
        reports.append(
            _migrate_global_assets(
                data_root,
                storage=storage,
                apply=args.apply,
                delete_local=args.delete_local,
                checkpoint_dir=checkpoint_dir,
            )
        )
    for name in project_names:
        project_path = data_root / name
        if not project_path.is_dir():
            raise FileNotFoundError(f"项目不存在: {name}")
        reports.append(
            _migrate_project(
                project_path,
                storage=storage,
                apply=args.apply,
                delete_local=args.delete_local,
                checkpoint_dir=checkpoint_dir,
            )
        )
    print(json.dumps({"dry_run": not args.apply, "projects": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (MediaStorageError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

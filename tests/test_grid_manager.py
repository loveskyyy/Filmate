"""Tests for GridManager file-based CRUD."""

import lib.grid_manager as grid_manager_module
from lib.grid.models import GridGeneration
from lib.grid_manager import GridManager


def _make_grid(**kwargs) -> GridGeneration:
    defaults = dict(
        episode=1,
        script_file="ep1.json",
        scene_ids=["S1", "S2", "S3", "S4"],
        rows=2,
        cols=2,
        grid_size="grid_4",
        provider="test",
        model="m",
    )
    defaults.update(kwargs)
    return GridGeneration.create(**defaults)


class TestGridManager:
    def test_cloud_storage_syncs_metadata_and_deletes_before_local(self, tmp_path, monkeypatch):
        calls: list[tuple[str, tuple[str, ...]]] = []

        class _Storage:
            def materialize_project_file(self, project_path, relative_path):
                return project_path / relative_path

            def sync_project_paths(self, _project_path, relative_paths):
                calls.append(("sync", tuple(str(path) for path in relative_paths)))

            def delete_project_paths(self, _project_name, relative_paths):
                paths = tuple(str(path) for path in relative_paths)
                assert (tmp_path / paths[0]).exists()
                assert not (tmp_path / paths[1]).exists()
                calls.append(("delete", paths))

        monkeypatch.setattr(grid_manager_module, "get_media_storage", lambda _root: _Storage())
        gm = GridManager(tmp_path)
        grid = _make_grid()
        gm.save(grid)

        assert gm.delete(grid.id) is True
        assert calls == [
            ("sync", (f"grids/{grid.id}.json",)),
            ("delete", (f"grids/{grid.id}.json", f"grids/{grid.id}.png")),
        ]

    def test_save_and_load(self, tmp_path):
        gm = GridManager(tmp_path)
        grid = _make_grid()
        gm.save(grid)
        loaded = gm.get(grid.id)
        assert loaded is not None
        assert loaded.id == grid.id
        assert loaded.scene_ids == ["S1", "S2", "S3", "S4"]
        assert len(loaded.frame_chain) == 4

    def test_list_grids(self, tmp_path):
        gm = GridManager(tmp_path)
        for _ in range(3):
            gm.save(_make_grid())
        assert len(gm.list_all()) == 3

    def test_update_status(self, tmp_path):
        gm = GridManager(tmp_path)
        grid = _make_grid()
        gm.save(grid)
        grid.status = "completed"
        gm.save(grid)
        assert gm.get(grid.id).status == "completed"

    def test_get_nonexistent(self, tmp_path):
        assert GridManager(tmp_path).get("nonexistent") is None

    def test_grids_dir_created(self, tmp_path):
        """GridManager creates the grids/ subdirectory automatically."""
        new_dir = tmp_path / "project"
        GridManager(new_dir)
        assert (new_dir / "grids").is_dir()

    def test_list_all_sorted_by_created_at(self, tmp_path):
        """list_all returns grids in ascending created_at order."""
        gm = GridManager(tmp_path)
        grids = [_make_grid() for _ in range(3)]
        for g in grids:
            gm.save(g)
        loaded = gm.list_all()
        assert [g.id for g in loaded] == [g.id for g in sorted(grids, key=lambda g: g.created_at)]

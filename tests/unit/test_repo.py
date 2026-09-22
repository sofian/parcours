import pytest
from pathlib import Path
from parcours.core.repo import find_data_repo, DataRepoNotFound, MARKER_FILENAME


def test_finds_marker_in_current_directory(tmp_path):
    (tmp_path / MARKER_FILENAME).write_text("name: test\n")
    assert find_data_repo(start=tmp_path, env={}) == tmp_path


def test_finds_marker_in_parent_directory(tmp_path):
    (tmp_path / MARKER_FILENAME).write_text("name: test\n")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert find_data_repo(start=nested, env={}) == tmp_path


def test_env_var_overrides_marker_search(tmp_path):
    marker_dir = tmp_path / "marker_repo"
    marker_dir.mkdir()
    (marker_dir / MARKER_FILENAME).write_text("name: test\n")
    env_dir = tmp_path / "env_repo"
    env_dir.mkdir()
    result = find_data_repo(start=marker_dir, env={"PARCO_DATA_DIR": str(env_dir)})
    assert result == env_dir


def test_explicit_path_overrides_everything(tmp_path):
    marker_dir = tmp_path / "marker_repo"
    marker_dir.mkdir()
    (marker_dir / MARKER_FILENAME).write_text("name: test\n")
    explicit_dir = tmp_path / "explicit_repo"
    explicit_dir.mkdir()
    result = find_data_repo(
        start=marker_dir,
        env={"PARCO_DATA_DIR": str(marker_dir)},
        explicit=explicit_dir,
    )
    assert result == explicit_dir


def test_falls_back_to_config_file(tmp_path, monkeypatch):
    config_home = tmp_path / "home"
    config_dir = config_home / ".config" / "parco"
    config_dir.mkdir(parents=True)
    data_repo = tmp_path / "configured_repo"
    data_repo.mkdir()
    (config_dir / "config.yaml").write_text(f"data_dir: {data_repo}\n")
    monkeypatch.setattr(Path, "home", lambda: config_home)

    no_marker_dir = tmp_path / "no_marker"
    no_marker_dir.mkdir()
    result = find_data_repo(start=no_marker_dir, env={})
    assert result == data_repo


def test_raises_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty_home")
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    with pytest.raises(DataRepoNotFound):
        find_data_repo(start=isolated, env={})


def test_explicit_path_must_exist(tmp_path):
    with pytest.raises(DataRepoNotFound):
        find_data_repo(explicit=tmp_path / "does_not_exist")

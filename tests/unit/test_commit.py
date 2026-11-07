import subprocess

from parcours.core.commit import commit_pending


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "widgets.csv").write_text("id,title_en\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, check=True, capture_output=True)


def test_commit_pending_commits_everything_with_generated_message(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "widgets.csv").write_text("id,title_en\nabc123,A\n", encoding="utf-8")
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "gadgets.csv").write_text("id,title_en\nzzz999,Z\n", encoding="utf-8")

    result = commit_pending(tmp_path)

    assert result.committed is True
    assert sorted(result.files) == ["entries/gadgets.csv", "widgets.csv"]
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=tmp_path, check=True, capture_output=True, text=True)
    assert "widgets.csv" in log.stdout
    assert "entries/gadgets.csv" in log.stdout


def test_commit_pending_uses_custom_message(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "widgets.csv").write_text("id,title_en\nabc123,A\n", encoding="utf-8")

    result = commit_pending(tmp_path, message="Imported from CCV export")

    assert result.committed is True
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=tmp_path, check=True, capture_output=True, text=True)
    assert log.stdout.strip() == "Imported from CCV export"


def test_commit_pending_does_nothing_on_clean_tree(tmp_path):
    _init_git_repo(tmp_path)

    result = commit_pending(tmp_path)

    assert result.committed is False
    assert result.files == []


def test_commit_pending_skips_lock_files_and_stray_root_files(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "grants.csv").write_text("id\n", encoding="utf-8")
    (tmp_path / "entries" / ".~lock.grants.csv#").write_text("lock", encoding="utf-8")
    (tmp_path / ".~lock.review.csv#").write_text("lock", encoding="utf-8")
    (tmp_path / "review.csv").write_text("scratch\n", encoding="utf-8")
    (tmp_path / "views.yaml").write_text("{}\n", encoding="utf-8")

    result = commit_pending(tmp_path)

    assert result.committed is True
    assert result.files == ["entries/grants.csv", "views.yaml"]
    assert result.skipped == [".~lock.review.csv#", "entries/.~lock.grants.csv#", "review.csv"]
    tracked = subprocess.run(["git", "ls-files"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.split()
    assert "review.csv" not in tracked
    assert "entries/.~lock.grants.csv#" not in tracked


def test_commit_pending_picks_up_new_files_next_to_tracked_ones(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "csl").mkdir()
    (tmp_path / "csl" / "apa.csl").write_text("<style/>", encoding="utf-8")
    subprocess.run(["git", "add", "csl"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Added csl"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "csl" / "mla.csl").write_text("<style/>", encoding="utf-8")

    result = commit_pending(tmp_path)

    assert result.files == ["csl/mla.csl"]


def test_commit_pending_stages_deletion_of_a_committed_lock_file(tmp_path):
    _init_git_repo(tmp_path)
    lock = tmp_path / ".~lock.widgets.csv#"
    lock.write_text("lock", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Oops"], cwd=tmp_path, check=True, capture_output=True)
    lock.unlink()

    result = commit_pending(tmp_path)

    assert result.files == [".~lock.widgets.csv#"]
    tracked = subprocess.run(["git", "ls-files"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.split()
    assert ".~lock.widgets.csv#" not in tracked


def test_commit_pending_reports_skipped_files_even_when_nothing_to_commit(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "notes.csv").write_text("x\n", encoding="utf-8")

    result = commit_pending(tmp_path)

    assert result.committed is False
    assert result.skipped == ["notes.csv"]

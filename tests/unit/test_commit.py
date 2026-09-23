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
    (tmp_path / "gadgets.csv").write_text("id,title_en\n", encoding="utf-8")
    (tmp_path / "gadgets.csv").write_text("id,title_en\nzzz999,Z\n", encoding="utf-8")

    result = commit_pending(tmp_path)

    assert result.committed is True
    assert sorted(result.files) == ["gadgets.csv", "widgets.csv"]
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=tmp_path, check=True, capture_output=True, text=True)
    assert "widgets.csv" in log.stdout
    assert "gadgets.csv" in log.stdout


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

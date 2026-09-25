import subprocess

from parcours.core.entries import add_entry, edit_entry
from parcours.core.schema import CategorySchema, FieldSpec


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    # Create an initial commit so git log and status work properly
    (path / ".gitkeep").touch()
    subprocess.run(["git", "add", ".gitkeep"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, check=True, capture_output=True)


def _commit_count(path):
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=path, check=True, capture_output=True, text=True
    ).stdout
    return len(log.splitlines())


def test_add_entry_creates_a_real_git_commit(tmp_path):
    _init_git_repo(tmp_path)
    schema = CategorySchema(
        name="widgets",
        fields=[FieldSpec(name="id", generated=True), FieldSpec(name="title_en", required=True)],
    )

    row = add_entry(tmp_path, schema, {"title_en": "A Widget"})

    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
    assert f"Added widgets entry {row['id']}" in log


def test_add_entry_commits_when_csv_was_already_tracked_and_clean(tmp_path):
    _init_git_repo(tmp_path)
    schema = CategorySchema(
        name="widgets",
        fields=[FieldSpec(name="id", generated=True), FieldSpec(name="title_en", required=True)],
    )
    # Pre-create and commit the CSV as an ordinary tracked, clean file —
    # this is the realistic steady-state (parco init already committed
    # every starter category's CSV), distinct from the untracked-first-row
    # scenario the test above this one covers. If is_file_dirty were ever
    # called AFTER write_all_rows instead of before, this exact scenario
    # would wrongly see the write's own diff as "already dirty" and skip
    # the commit.
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,title_en\n", encoding="utf-8")
    subprocess.run(["git", "add", "entries/widgets.csv"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add entries/widgets.csv"], cwd=tmp_path, check=True, capture_output=True)
    commits_before = _commit_count(tmp_path)

    row = add_entry(tmp_path, schema, {"title_en": "A Widget"})

    assert _commit_count(tmp_path) == commits_before + 1
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
    assert f"Added widgets entry {row['id']}" in log


def test_edit_entry_with_no_changes_does_not_raise_or_create_a_spurious_commit(tmp_path):
    _init_git_repo(tmp_path)
    schema = CategorySchema(
        name="widgets",
        fields=[FieldSpec(name="id", generated=True), FieldSpec(name="title_en", required=True)],
    )

    row = add_entry(tmp_path, schema, {"title_en": "A Widget"})
    commits_before = _commit_count(tmp_path)

    # Edit with values identical to what's already on disk — a true no-op.
    updated = edit_entry(tmp_path, schema, row["id"], {"title_en": "A Widget"})

    assert updated == row
    assert _commit_count(tmp_path) == commits_before

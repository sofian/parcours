import subprocess

from parcours.core.entries import add_entry
from parcours.core.schema import CategorySchema, FieldSpec


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)


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

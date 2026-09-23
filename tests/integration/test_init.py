import subprocess

import pytest
import yaml

from parcours.core.init import GitInitFailed, InitAnswers, RepoAlreadyExists, scaffold_repo
from parcours.core.schema import load_all_schemas


def _answers(**overrides) -> InitAnswers:
    defaults = dict(
        first_name="Jane",
        last_name="Doe",
        variant_name="academic",
        languages=["en"],
        currency="CAD",
        title_en="Associate Professor",
    )
    defaults.update(overrides)
    return InitAnswers(**defaults)


def _set_git_env(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


def test_scaffold_repo_creates_every_expected_file(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers())

    assert (repo / "parco.yaml").is_file()
    assert (repo / "vocab.yaml").is_file()
    assert (repo / "translations.csv").is_file()
    assert (repo / "views.yaml").is_file()
    assert (repo / "identity.yaml").is_file()
    assert (repo / "profiles" / "academic-en.yaml").is_file()

    schemas = load_all_schemas(repo / "categories")
    assert len(schemas) == 19
    for name, schema in schemas.items():
        csv_path = repo / f"{name}.csv"
        assert csv_path.is_file()
        header = csv_path.read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == schema.field_names()


def test_scaffold_repo_refuses_if_parco_yaml_already_exists(tmp_path):
    repo = tmp_path / "existing"
    repo.mkdir()
    (repo / "parco.yaml").write_text("currency: {default: CAD, report: CAD}\n")

    with pytest.raises(RepoAlreadyExists):
        scaffold_repo(repo, _answers())

    assert not (repo / "vocab.yaml").exists()


def test_scaffold_repo_writes_currency_to_both_default_and_report(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers(currency="EUR"))

    config = yaml.safe_load((repo / "parco.yaml").read_text(encoding="utf-8"))
    assert config == {"currency": {"default": "EUR", "report": "EUR"}}


def test_scaffold_repo_writes_a_flat_profile_for_one_language(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers(languages=["en"]))

    assert (repo / "profiles" / "academic-en.yaml").is_file()
    assert not (repo / "profiles" / "_academic.yaml").exists()
    profile = yaml.safe_load((repo / "profiles" / "academic-en.yaml").read_text(encoding="utf-8"))
    assert profile["meta"]["language"] == "en"
    assert "extends" not in profile
    assert len(profile["sections"]) == 18  # every non-skills view


def test_scaffold_repo_writes_a_base_plus_extends_children_for_two_languages(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers(languages=["en", "fr"], title_fr="Professeure agrégée"))

    base = yaml.safe_load((repo / "profiles" / "_academic.yaml").read_text(encoding="utf-8"))
    assert "language" not in base["meta"]
    assert len(base["sections"]) == 18

    en_child = yaml.safe_load((repo / "profiles" / "academic-en.yaml").read_text(encoding="utf-8"))
    assert en_child == {"extends": "_academic", "meta": {"language": "en"}}
    fr_child = yaml.safe_load((repo / "profiles" / "academic-fr.yaml").read_text(encoding="utf-8"))
    assert fr_child == {"extends": "_academic", "meta": {"language": "fr"}}


def test_scaffold_repo_omits_blank_optional_identity_fields(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers(phone="", homepage=""))

    identity = yaml.safe_load((repo / "identity.yaml").read_text(encoding="utf-8"))
    variant = identity["variants"]["academic"]
    assert "phone" not in variant
    assert "homepage" not in variant
    assert variant["title_en"] == "Associate Professor"


def test_scaffold_repo_generated_sections_use_the_generic_order_by_rule(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers())

    profile = yaml.safe_load((repo / "profiles" / "academic-en.yaml").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in profile["sections"]}
    assert by_id["grants"]["order_by"] == "start_date desc"
    assert by_id["artworks"]["order_by"] == "date desc"
    assert "order_by" not in by_id["publications"]


def test_scaffold_repo_creates_a_real_git_repo_with_one_commit(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers())

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert len(log.splitlines()) == 1
    assert "Initialized parco data repo" in log

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert status.strip() == ""


def test_scaffold_repo_wraps_git_failure(tmp_path, monkeypatch):
    def _fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "git", stderr=b"fatal: unable to auto-detect email address")

    monkeypatch.setattr("parcours.core.init.subprocess.run", _fail)
    repo = tmp_path / "my-cv"

    with pytest.raises(GitInitFailed):
        scaffold_repo(repo, _answers())

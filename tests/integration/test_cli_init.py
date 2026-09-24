from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()


def _git_env(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


def test_init_scaffolds_a_repo_for_a_single_language(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    target = tmp_path / "my-cv"

    # first, last, variant(default), language choice(1=en), title_en,
    # email, phone(skip), homepage(skip), currency, citation export(skip), confirm
    result = runner.invoke(
        app,
        ["init", str(target)],
        input="Jane\nDoe\n\n1\nAssociate Professor\njane@example.edu\n\n\nCAD\n\ny\n",
    )

    assert result.exit_code == 0, result.stdout
    assert (target / "parco.yaml").is_file()
    assert (target / "profiles" / "academic-en.yaml").is_file()
    assert "Initialized a new parco data repo" in result.stdout


def test_init_scaffolds_a_bilingual_repo(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    target = tmp_path / "my-cv"

    # first, last, variant(default), language choice(3=both),
    # title_en, title_fr, email, phone(skip), homepage(skip), currency, citation export(skip), confirm
    result = runner.invoke(
        app,
        ["init", str(target)],
        input="Jane\nDoe\n\n3\nAssociate Professor\nProfesseure agrégée\njane@example.edu\n\n\nCAD\n\ny\n",
    )

    assert result.exit_code == 0, result.stdout
    assert (target / "profiles" / "_academic.yaml").is_file()
    assert (target / "profiles" / "academic-en.yaml").is_file()
    assert (target / "profiles" / "academic-fr.yaml").is_file()


def test_init_aborts_when_confirm_declined(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    target = tmp_path / "my-cv"

    result = runner.invoke(
        app,
        ["init", str(target)],
        input="Jane\nDoe\n\n1\nAssociate Professor\njane@example.edu\n\n\nCAD\n\nn\n",
    )

    assert result.exit_code == 0
    assert "Aborted" in result.stdout
    assert not (target / "parco.yaml").exists()


def test_init_refuses_before_prompting_if_repo_already_exists(tmp_path, monkeypatch):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "parco.yaml").write_text("currency: {default: CAD, report: CAD}\n")

    result = runner.invoke(app, ["init", str(target)])

    assert result.exit_code == 1
    assert "already exists" in result.stdout


def test_init_phone_prompt_hints_international_format(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    target = tmp_path / "my-cv"

    result = runner.invoke(
        app,
        ["init", str(target)],
        input="Jane\nDoe\n\n1\nAssociate Professor\njane@example.edu\n\n\nCAD\n\ny\n",
    )

    assert result.exit_code == 0, result.stdout
    assert "+1 514 987 3000" in result.stdout
    assert "international format" in result.stdout


def test_init_writes_a_provided_citation_export_path(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    target = tmp_path / "my-cv"

    result = runner.invoke(
        app,
        ["init", str(target)],
        input="Jane\nDoe\n\n1\nAssociate Professor\njane@example.edu\n\n\nCAD\n/home/jane/Zotero/library.json\ny\n",
    )

    assert result.exit_code == 0, result.stdout
    assert "Citation export: /home/jane/Zotero/library.json" in result.stdout
    content = (target / "categories" / "publications.yaml").read_text(encoding="utf-8")
    assert "json: /home/jane/Zotero/library.json" in content


def test_init_rejects_variant_name_with_path_separator(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    target = tmp_path / "my-cv"

    # first, last, variant(rejected: contains '/'), variant(retry, valid),
    # language choice(1=en), title_en, email, phone(skip), homepage(skip),
    # currency, citation export(skip), confirm
    result = runner.invoke(
        app,
        ["init", str(target)],
        input="Jane\nDoe\n../../pwned\nacademic\n1\nAssociate Professor\njane@example.edu\n\n\nCAD\n\ny\n",
    )

    assert result.exit_code == 0, result.stdout
    assert "can't contain" in result.stdout
    assert (target / "parco.yaml").is_file()
    assert (target / "profiles" / "academic-en.yaml").is_file()

    # nothing should have been written outside the target repo
    assert not list(tmp_path.parent.glob("*pwned*"))
    assert not list(tmp_path.glob("*pwned*"))
    assert not any(tmp_path.rglob("*pwned*"))


def test_init_refuses_before_prompting_if_git_identity_is_missing(tmp_path, monkeypatch):
    target = tmp_path / "my-cv"

    def _raise_identity_missing():
        from parcours.core.init import GitIdentityMissing
        raise GitIdentityMissing(
            'Git author identity isn\'t configured, so the final commit would fail. Run:\n'
            '  git config --global user.email "you@example.com"\n'
            '  git config --global user.name "Your Name"\n'
            "then try again.\n"
        )

    monkeypatch.setattr("parcours.cli.main.check_git_identity_configured", _raise_identity_missing)

    # No input supplied at all — proves the refusal happens before any prompt is reached.
    result = runner.invoke(app, ["init", str(target)])

    assert result.exit_code == 1
    assert "git config --global" in result.stdout
    assert not target.exists()


def test_init_defaults_to_the_current_directory(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["init"],
        input="Jane\nDoe\n\n1\nAssociate Professor\njane@example.edu\n\n\nCAD\n\ny\n",
    )

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "parco.yaml").is_file()

from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()


def _setup_data_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "grants.yaml").write_text("""
name: grants
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
  - {name: title_fr}
  - {name: funder, required: true}
  - {name: role, required: true}
  - {name: start_date, type: date, precision: month, required: true}
  - {name: end_date, type: date, precision: month}
""")
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "translations.csv").write_text(
        "id,category,en,fr\ngrants,section,Grants,Subventions\n"
    )
    (tmp_path / "identity.yaml").write_text("""
name:
  first: Jane
  last: Doe
variants:
  academic:
    email: jane@example.edu
""")
    (tmp_path / "views.yaml").write_text("""
grants:
  source: grants
  entry_type: NormalEntry
  fields:
    name: "{title}"
    start_date: start_date
    end_date: end_date
""")
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "academic-en.yaml").write_text("""
meta:
  name: academic
  language: en
  format: pdf
  theme: sb2nov
  identity_variant: academic
sections:
  - id: grants
    source: grants
""")
    return tmp_path


def test_build_writes_the_rendered_file(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    def _fake_render(cmd, check, capture_output, text):
        # cmd = ["rendercv", "render", <input>, path_flag, <output>, ...disable_flags]
        output_path = cmd[4]
        __import__("pathlib").Path(output_path).write_bytes(b"fake pdf bytes")

    monkeypatch.setattr("parcours.core.build.subprocess.run", _fake_render)

    result = runner.invoke(app, ["build", "--profile", "academic-en"])

    assert result.exit_code == 0, result.stdout
    assert (repo / "build" / "cv-academic-en.pdf").is_file()


def test_build_refuses_on_lint_error_without_force(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,,,,,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["build", "--profile", "academic-en"])

    assert result.exit_code == 1, result.stdout
    assert "lint error" in result.stdout


def test_build_force_bypasses_lint_gate(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,,,,,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    def _fake_render(cmd, check, capture_output, text):
        output_path = cmd[4]
        __import__("pathlib").Path(output_path).write_bytes(b"fake pdf bytes")

    monkeypatch.setattr("parcours.core.build.subprocess.run", _fake_render)

    result = runner.invoke(app, ["build", "--profile", "academic-en", "--force"])

    assert result.exit_code == 0, result.stdout


def test_build_rejects_docx(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["build", "--profile", "academic-en", "--format", "docx"])

    assert result.exit_code == 1
    assert "not yet supported" in result.stdout


def test_build_unknown_profile_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["build", "--profile", "nonexistent"])

    assert result.exit_code == 2
    assert "profile" in result.stdout.lower()


def test_build_respects_custom_output_dir(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    def _fake_render(cmd, check, capture_output, text):
        output_path = cmd[4]
        __import__("pathlib").Path(output_path).write_bytes(b"fake pdf bytes")

    monkeypatch.setattr("parcours.core.build.subprocess.run", _fake_render)

    result = runner.invoke(
        app, ["build", "--profile", "academic-en", "--output-dir", str(tmp_path / "custom")]
    )

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "custom" / "cv-academic-en.pdf").is_file()

import subprocess

from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()

_EDUCATION_SCHEMA = """
name: education
handler: generic
fields:
  - {name: id, generated: true}
  - {name: degree_type, required: true}
  - {name: degree_name_en}
  - {name: degree_name_fr}
  - {name: specialization_en}
  - {name: specialization_fr}
  - {name: organization, required: true}
  - {name: degree_status, required: true}
  - {name: start_date, type: date, precision: month, required: true}
  - {name: end_date, type: date, precision: month}
  - {name: thesis_title}
  - {name: advisor}
  - {name: note_en}
  - {name: note_fr}
dedup:
  - when: [{exact: organization}, {exact: degree_type}, {same_year: start_date}]
    as: duplicate
"""

_SAMPLE_XML = """<?xml version="1.0"?>
<generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
  <section label="Education">
    <section label="Degrees" recordId="r1">
      <field label="Degree Type"><lov id="1">Doctorate</lov></field>
      <field label="Degree Status"><lov id="2">Completed</lov></field>
      <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
    </section>
  </section>
</generic-cv:generic-cv>
"""


def _setup_data_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("currency:\n  default: CAD\n  report: CAD\n", encoding="utf-8")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "education.yaml").write_text(_EDUCATION_SCHEMA, encoding="utf-8")
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "education.csv").write_text(
        "id,degree_type,degree_name_en,degree_name_fr,specialization_en,specialization_fr,"
        "organization,degree_status,start_date,end_date,thesis_title,advisor,note_en,note_fr\n",
        encoding="utf-8",
    )
    (tmp_path / "identity.yaml").write_text("name:\n  first: Jane\n  last: Doe\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_import_ccv_dry_run_writes_nothing(tmp_path, tmp_path_factory, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    # The export file must live OUTSIDE the git repo under test — writing it
    # inside `tmp_path` would show up as an untracked file in every
    # `git status --porcelain` assertion below, regardless of command behavior.
    xml_path = tmp_path_factory.mktemp("ccv_export") / "export.xml"
    xml_path.write_text(_SAMPLE_XML, encoding="utf-8")

    result = runner.invoke(app, ["import", "ccv", "--file", str(xml_path), "--dry-run"])

    assert result.exit_code == 0
    assert "education" in result.stdout.lower()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True)
    assert status.stdout.strip() == ""


def test_import_ccv_confirm_writes_uncommitted(tmp_path, tmp_path_factory, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    xml_path = tmp_path_factory.mktemp("ccv_export") / "export.xml"
    xml_path.write_text(_SAMPLE_XML, encoding="utf-8")

    result = runner.invoke(app, ["import", "ccv", "--file", str(xml_path)], input="y\n")

    assert result.exit_code == 0
    content = (repo / "entries" / "education.csv").read_text(encoding="utf-8")
    assert "doctorate" in content
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True)
    assert "entries/education.csv" in status.stdout
    assert "parco commit" in result.stdout


def test_import_ccv_decline_writes_nothing(tmp_path, tmp_path_factory, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    xml_path = tmp_path_factory.mktemp("ccv_export") / "export.xml"
    xml_path.write_text(_SAMPLE_XML, encoding="utf-8")

    result = runner.invoke(app, ["import", "ccv", "--file", str(xml_path)], input="n\n")

    assert result.exit_code == 0
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True)
    assert status.stdout.strip() == ""

from parcours.core.views import load_views


def test_load_views_parses_source_entry_type_and_fields(tmp_path):
    path = tmp_path / "views.yaml"
    path.write_text("""
grants:
  source: grants
  entry_type: NormalEntry
  fields:
    name: "{title}"
    start_date: start_date
    end_date: end_date
    highlights:
      - "{funder} — {role}"
""", encoding="utf-8")

    views = load_views(path)

    assert set(views.keys()) == {"grants"}
    view = views["grants"]
    assert view.name == "grants"
    assert view.source == "grants"
    assert view.entry_type == "NormalEntry"
    assert view.fields["name"] == "{title}"
    assert view.fields["highlights"] == ["{funder} — {role}"]
    assert view.group_by is None


def test_load_views_parses_group_by(tmp_path):
    path = tmp_path / "views.yaml"
    path.write_text("""
skills-terms:
  source: skills
  entry_type: OneLineEntry
  group_by: category
  fields:
    label: "{category}"
""", encoding="utf-8")

    views = load_views(path)

    assert views["skills-terms"].group_by == "category"


def test_load_views_supports_multiple_views(tmp_path):
    path = tmp_path / "views.yaml"
    path.write_text("""
grants:
  source: grants
  entry_type: NormalEntry
  fields: {name: "{title}"}
education:
  source: education
  entry_type: EducationEntry
  fields: {institution: organization}
""", encoding="utf-8")

    views = load_views(path)

    assert set(views.keys()) == {"grants", "education"}

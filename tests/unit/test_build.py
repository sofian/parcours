import json

from parcours.core.build import build_rendercv_data
from parcours.core.profiles import Profile


def _setup_data_repo(tmp_path):
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "grants.yaml").write_text("""
name: grants
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en}
  - {name: title_fr}
  - {name: funder, required: true}
  - {name: role, required: true}
  - {name: start_date, type: date, precision: month, required: true}
  - {name: end_date, type: date, precision: month}
  - {name: amount}
  - {name: currency}
  - {name: co_investigators}
""")
    (tmp_path / "categories" / "publications.yaml").write_text("""
name: publications
handler: publications
options:
  json: zotero/library.json
fields:
  - {name: id, generated: true}
  - {name: citekey, required: true}
""")
    (tmp_path / "translations.csv").write_text(
        "id,category,en,fr\n"
        "grants,section,Grants,Subventions\n"
        "publications,section,Publications,Publications\n"
    )
    (tmp_path / "identity.yaml").write_text("""
name:
  first: Jane
  last: Doe
variants:
  academic:
    email: jane@example.edu
    title_en: "Associate Professor"
    title_fr: "Professeure agrégée"
""")
    return tmp_path


def _grants_view():
    from parcours.core.views import ViewSpec
    return ViewSpec(
        name="grants", source="grants", entry_type="NormalEntry",
        fields={
            "name": "{title}",
            "start_date": "start_date",
            "end_date": "end_date",
            "highlights": ["{funder} — {role}"],
        },
    )


def _publications_view():
    from parcours.core.views import ViewSpec
    return ViewSpec(
        name="publications", source="publications", entry_type="PublicationEntry",
        fields={
            "title": "{zotero_title}",
            "authors": "{zotero_authors}",
            "date": "{zotero_date}",
        },
    )


def test_build_resolves_identity_into_cv_block(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    profile = Profile(meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"}, sections=[])
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {})

    data = build_rendercv_data(repo, profile)

    assert data["cv"]["name"] == "Jane Doe"
    assert data["cv"]["headline"] == "Associate Professor"
    assert data["cv"]["email"] == "jane@example.edu"
    assert data["design"]["theme"] == "sb2nov"


def test_build_resolves_a_section_title_from_translations(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01,50000,CAD,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})

    data = build_rendercv_data(repo, profile)

    assert "Grants" in data["cv"]["sections"]
    assert "Subventions" not in data["cv"]["sections"]


def test_build_maps_grant_rows_into_normal_entries(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01,50000,CAD,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})

    data = build_rendercv_data(repo, profile)

    entries = data["cv"]["sections"]["Grants"]
    assert len(entries) == 1
    assert entries[0]["name"] == "Big Grant"
    assert entries[0]["start_date"] == "2020-01"
    assert entries[0]["end_date"] == "2022-01"
    assert entries[0]["highlights"] == ["FRQSC — PI"]


def test_build_respects_section_filter_order_by_and_limit(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,First,Premier,FRQSC,PI,2020-01,2021-01,,,\n"
        "g2,Second,Deuxieme,SSHRC,co-PI,2019-01,2020-06,,,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants", "order_by": "start_date desc", "limit": 1}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})

    data = build_rendercv_data(repo, profile)

    entries = data["cv"]["sections"]["Grants"]
    assert len(entries) == 1
    assert entries[0]["name"] == "First"


def test_build_merges_zotero_fields_for_publications_backed_handler(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "zotero").mkdir()
    (repo / "zotero" / "library.json").write_text(json.dumps([
        {
            "id": "doe2024widgets",
            "title": "On Widgets",
            "author": [{"given": "Jane", "family": "Doe"}],
            "issued": {"date-parts": [[2024, 3]]},
        }
    ]))
    (repo / "publications.csv").write_text("id,citekey\np1,doe2024widgets\n")
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "publications", "source": "publications"}],
    )
    monkeypatch.setattr(
        "parcours.core.build.load_views", lambda path: {"publications": _publications_view()}
    )

    data = build_rendercv_data(repo, profile)

    entries = data["cv"]["sections"]["Publications"]
    assert len(entries) == 1
    assert entries[0]["title"] == "On Widgets"
    assert entries[0]["authors"] == ["Jane Doe"]
    assert entries[0]["date"] == "2024-03"


def test_build_leaves_zotero_fields_absent_for_an_unresolved_citekey(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "zotero").mkdir()
    (repo / "zotero" / "library.json").write_text(json.dumps([]))
    (repo / "publications.csv").write_text("id,citekey\np1,nonexistent-key\n")
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "publications", "source": "publications"}],
    )
    monkeypatch.setattr(
        "parcours.core.build.load_views", lambda path: {"publications": _publications_view()}
    )

    data = build_rendercv_data(repo, profile)

    entries = data["cv"]["sections"]["Publications"]
    assert len(entries) == 1
    assert "title" not in entries[0]
    assert "authors" not in entries[0]


import pytest

from parcours.core.build import BuildError, run_build


def test_run_build_refuses_when_a_referenced_category_has_a_lint_error(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    # A grant missing its required `funder` — a real lint error.
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,,PI,2020-01,2022-01,,,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})

    with pytest.raises(BuildError, match="grants"):
        run_build(repo, profile, "pdf", tmp_path / "out", force=False)


def test_run_build_force_skips_the_lint_gate(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,,PI,2020-01,2022-01,,,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov", "output": "cv-test"},
        sections=[{"id": "grants", "source": "grants"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})
    monkeypatch.setattr("parcours.core.build.subprocess.run", lambda *a, **k: None)

    output_dir = tmp_path / "out"
    result = run_build(repo, profile, "pdf", output_dir, force=True)

    assert result == output_dir / "cv-test.pdf"


def test_run_build_rejects_unsupported_format(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov", "output": "cv-test"},
        sections=[],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {})

    with pytest.raises(BuildError, match="docx"):
        run_build(repo, profile, "docx", tmp_path / "out", force=True)


def test_run_build_wraps_a_rendercv_failure(tmp_path, monkeypatch):
    import subprocess

    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov", "output": "cv-test"},
        sections=[],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {})

    def _fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "rendercv", stderr="bad theme")

    monkeypatch.setattr("parcours.core.build.subprocess.run", _fail)

    with pytest.raises(BuildError, match="bad theme"):
        run_build(repo, profile, "pdf", tmp_path / "out", force=True)


def test_run_build_failure_message_includes_rendercv_stdout(tmp_path, monkeypatch):
    """RenderCV prints its validation-error table to stdout, not stderr."""
    import subprocess

    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov", "output": "cv-test"},
        sections=[],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {})

    def _fail(*args, **kwargs):
        # `output=` is the constructor's name for what reads back as
        # `.stdout` on the raised exception.
        raise subprocess.CalledProcessError(
            1, "rendercv", output="Error: invalid theme name", stderr=""
        )

    monkeypatch.setattr("parcours.core.build.subprocess.run", _fail)

    with pytest.raises(BuildError, match="invalid theme name"):
        run_build(repo, profile, "pdf", tmp_path / "out", force=True)


# --- View name vs. category name ---------------------------------------


def _renamed_grants_view():
    """A view whose dict key (`grants-recent`) differs from the category
    it reads (`grants`) — perfectly legal in views.yaml."""
    from parcours.core.views import ViewSpec
    return ViewSpec(
        name="grants-recent", source="grants", entry_type="NormalEntry",
        fields={"name": "{title}", "start_date": "start_date"},
    )


def test_lint_gate_uses_the_views_underlying_category_not_the_view_name(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    # A grant missing its required `funder` — a real lint error.
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,,PI,2020-01,2022-01,,,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants-recent"}],
    )
    monkeypatch.setattr(
        "parcours.core.build.load_views", lambda path: {"grants-recent": _renamed_grants_view()}
    )

    with pytest.raises(BuildError) as excinfo:
        run_build(repo, profile, "pdf", tmp_path / "out", force=False)

    assert "'grants'" in str(excinfo.value)
    assert "grants-recent" not in str(excinfo.value)


def test_build_rendercv_data_resolves_the_schema_via_the_views_source(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01,,,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants-recent"}],
    )
    monkeypatch.setattr(
        "parcours.core.build.load_views", lambda path: {"grants-recent": _renamed_grants_view()}
    )

    data = build_rendercv_data(repo, profile)

    assert data["cv"]["sections"]["Grants"][0]["name"] == "Big Grant"


# --- Glossary resolution ------------------------------------------------


def test_build_resolves_a_glossary_backed_field_through_translations(tmp_path, monkeypatch):
    from parcours.core.views import ViewSpec

    repo = _setup_data_repo(tmp_path)
    (repo / "categories" / "exhibitions.yaml").write_text("""
name: exhibitions
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en}
  - {name: location, glossary: location}
""")
    (repo / "translations.csv").write_text(
        "id,category,en,fr\n"
        "exhibitions,section,Exhibitions,Expositions\n"
        "montreal,location,\"Montreal, Canada\",\"Montréal, Canada\"\n"
    )
    (repo / "exhibitions.csv").write_text("id,title_en,location\ne1,A Show,montreal\n")
    view = ViewSpec(
        name="exhibitions", source="exhibitions", entry_type="NormalEntry",
        fields={"name": "{title}", "location": "{location}"},
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "exhibitions", "source": "exhibitions"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"exhibitions": view})

    data = build_rendercv_data(repo, profile)

    entry = data["cv"]["sections"]["Exhibitions"][0]
    assert entry["location"] == "Montreal, Canada"

    profile_fr = Profile(
        meta={"language": "fr", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "exhibitions", "source": "exhibitions"}],
    )
    data_fr = build_rendercv_data(repo, profile_fr)
    assert data_fr["cv"]["sections"]["Expositions"][0]["location"] == "Montréal, Canada"


def test_build_leaves_a_glossary_value_literal_when_unmatched(tmp_path, monkeypatch):
    from parcours.core.views import ViewSpec

    repo = _setup_data_repo(tmp_path)
    (repo / "categories" / "exhibitions.yaml").write_text("""
name: exhibitions
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en}
  - {name: location, glossary: location}
""")
    (repo / "exhibitions.csv").write_text("id,title_en,location\ne1,A Show,Reykjavik Iceland\n")
    view = ViewSpec(
        name="exhibitions", source="exhibitions", entry_type="NormalEntry",
        fields={"name": "{title}", "location": "{location}"},
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "exhibitions", "source": "exhibitions"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"exhibitions": view})

    data = build_rendercv_data(repo, profile)

    assert data["cv"]["sections"]["exhibitions"][0]["location"] == "Reykjavik Iceland"


# --- Locale block -------------------------------------------------------


def test_build_emits_a_locale_block_matching_the_profile_language(tmp_path, monkeypatch):
    """RenderCV localizes month names from `locale.language`, which takes a
    spelled-out locale name ("english"/"french"), not an ISO code."""
    repo = _setup_data_repo(tmp_path)
    (repo / "views.yaml").write_text("")
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {})

    profile_en = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"}, sections=[]
    )
    profile_fr = Profile(
        meta={"language": "fr", "identity_variant": "academic", "theme": "sb2nov"}, sections=[]
    )

    assert build_rendercv_data(repo, profile_en)["locale"] == {"language": "english"}
    assert build_rendercv_data(repo, profile_fr)["locale"] == {"language": "french"}

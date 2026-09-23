from parcours.core.profiles import load_profile


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_load_profile_without_extends(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "short.yaml", """
meta:
  name: short
  language: en
  format: pdf
  theme: sb2nov
  identity_variant: academic
sections:
  - id: publications
    source: publications
""")

    profile = load_profile(profiles_dir, "short")

    assert profile.meta["name"] == "short"
    assert profile.meta["language"] == "en"
    assert len(profile.sections) == 1
    assert profile.sections[0]["id"] == "publications"


def test_load_profile_merges_extends_base(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "_academic.yaml", """
meta:
  name: academic
  format: pdf
  theme: sb2nov
  identity_variant: academic
sections:
  - id: publications
    source: publications
  - id: grants
    source: grants
""")
    _write(profiles_dir / "academic-en.yaml", """
extends: _academic
meta:
  language: en
""")

    profile = load_profile(profiles_dir, "academic-en")

    assert profile.meta["name"] == "academic"
    assert profile.meta["format"] == "pdf"
    assert profile.meta["theme"] == "sb2nov"
    assert profile.meta["language"] == "en"
    assert len(profile.sections) == 2


def test_load_profile_child_can_override_a_base_meta_field(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "_academic.yaml", """
meta:
  name: academic
  theme: sb2nov
sections: []
""")
    _write(profiles_dir / "academic-short.yaml", """
extends: _academic
meta:
  language: en
  theme: engineeringresumes
""")

    profile = load_profile(profiles_dir, "academic-short")

    assert profile.meta["theme"] == "engineeringresumes"
    assert profile.meta["name"] == "academic"


def test_load_profile_child_can_fully_replace_sections(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "_academic.yaml", """
meta:
  name: academic
sections:
  - id: publications
    source: publications
  - id: grants
    source: grants
""")
    _write(profiles_dir / "academic-short.yaml", """
extends: _academic
meta:
  language: en
sections:
  - id: publications
    source: publications
""")

    profile = load_profile(profiles_dir, "academic-short")

    assert len(profile.sections) == 1


def test_profile_output_defaults_to_name_and_language(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "academic-en.yaml", """
meta:
  name: academic
  language: en
sections: []
""")

    profile = load_profile(profiles_dir, "academic-en")

    assert profile.output == "cv-academic-en"


def test_profile_output_uses_a_custom_template_from_meta(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "academic-en.yaml", """
meta:
  name: academic
  language: en
  output: "my-custom-cv"
sections: []
""")

    profile = load_profile(profiles_dir, "academic-en")

    assert profile.output == "my-custom-cv"


def test_profile_output_template_inherited_from_base_fills_child_language(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "_academic.yaml", """
meta:
  name: academic
  output: "cv-{name}-{language}"
sections: []
""")
    _write(profiles_dir / "academic-fr.yaml", """
extends: _academic
meta:
  language: fr
""")

    profile = load_profile(profiles_dir, "academic-fr")

    assert profile.output == "cv-academic-fr"

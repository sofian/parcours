import pytest

from parcours.core.identity import IdentityVariantNotFound, load_identity, resolve_identity


def _write_identity(tmp_path):
    path = tmp_path / "identity.yaml"
    path.write_text("""
name:
  first: Jane
  last: Doe
variants:
  artist:
    email: contact@example.com
    homepage: example.com
  academic:
    email: jane.doe@example.edu
    homepage: example.com
    phone: "+1 555-000-1111"
    title_en: "Associate Professor"
    title_fr: "Professeure agrégée"
""", encoding="utf-8")
    return path


def test_load_identity_reads_the_yaml(tmp_path):
    identity = load_identity(_write_identity(tmp_path))
    assert identity["name"]["first"] == "Jane"


def test_resolve_identity_builds_full_name_and_contact_fields(tmp_path):
    identity = load_identity(_write_identity(tmp_path))

    cv = resolve_identity(identity, "academic", "en")

    assert cv["name"] == "Jane Doe"
    assert cv["email"] == "jane.doe@example.edu"
    assert cv["phone"] == "+1 555-000-1111"
    assert cv["website"] == "example.com"


def test_resolve_identity_resolves_bilingual_title_by_language():
    identity = {
        "name": {"first": "Jane", "last": "Doe"},
        "variants": {"academic": {"title_en": "Associate Professor", "title_fr": "Professeure agrégée"}},
    }

    assert resolve_identity(identity, "academic", "en")["headline"] == "Associate Professor"
    assert resolve_identity(identity, "academic", "fr")["headline"] == "Professeure agrégée"


def test_resolve_identity_omits_headline_when_variant_has_no_title(tmp_path):
    identity = load_identity(_write_identity(tmp_path))

    cv = resolve_identity(identity, "artist", "en")

    assert "headline" not in cv


def test_resolve_identity_raises_for_unknown_variant(tmp_path):
    identity = load_identity(_write_identity(tmp_path))

    with pytest.raises(IdentityVariantNotFound, match="job-application"):
        resolve_identity(identity, "job-application", "en")

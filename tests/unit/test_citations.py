from pathlib import Path

import pytest

from parcours.core.citations import UnknownCitationStyle, render_citations, resolve_style

_BUNDLED_STYLES_DIR = Path(__file__).parent.parent.parent / "parcours" / "starter_config" / "csl_styles"


def _widget_record(citekey="doe2024widgets"):
    return {
        "id": citekey,
        "type": "article-journal",
        "title": "On Widgets",
        "author": [{"given": "Jane", "family": "Doe"}],
        "container-title": "Journal of Widgets",
        "issued": {"date-parts": [[2024, 3]]},
        "volume": "12",
        "page": "1-20",
    }


def test_resolve_style_maps_bundled_short_names():
    assert resolve_style("apa") == _BUNDLED_STYLES_DIR / "apa.csl"
    assert resolve_style("chicago-author-date") == _BUNDLED_STYLES_DIR / "chicago-author-date.csl"
    assert resolve_style("mla") == _BUNDLED_STYLES_DIR / "modern-language-association.csl"


def test_resolve_style_accepts_a_custom_path(tmp_path):
    custom = tmp_path / "custom.csl"
    custom.write_text("<style/>", encoding="utf-8")

    assert resolve_style(str(custom)) == custom


def test_resolve_style_rejects_an_unknown_name_or_missing_path():
    with pytest.raises(UnknownCitationStyle):
        resolve_style("not-a-real-style-or-path")


def test_render_citations_apa_italicizes_the_journal_title_as_markdown():
    style_path = resolve_style("apa")

    citations = render_citations([_widget_record()], style_path)

    assert len(citations) == 1
    assert "*Journal of Widgets*" in citations[0]
    assert "Doe" in citations[0]
    assert "2024" in citations[0]
    assert "<i>" not in citations[0]


def test_render_citations_preserves_registration_order():
    style_path = resolve_style("apa")
    records = [
        {
            "id": "zzz2020", "type": "article-journal", "title": "Zebra Study",
            "author": [{"given": "A", "family": "Zed"}], "container-title": "J",
            "issued": {"date-parts": [[2020]]},
        },
        {
            "id": "aaa2024", "type": "article-journal", "title": "Aardvark Study",
            "author": [{"given": "B", "family": "Aab"}], "container-title": "J",
            "issued": {"date-parts": [[2024]]},
        },
    ]

    citations = render_citations(records, style_path)

    assert "Zebra" in citations[0]
    assert "Aardvark" in citations[1]


def test_render_citations_empty_list_returns_empty_list():
    assert render_citations([], resolve_style("apa")) == []

"""Renders CSL-JSON records (already resolved via
`handlers.publications.PublicationsHandler.resolve`) as formatted
citations via citeproc-py (see SPECS.md, "Citation formatting"). Core
layer: no prompting, no printing — the CLI `list --format citation`
command owns all output."""

import warnings
from pathlib import Path

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle
from citeproc.source.json import CiteProcJSON

_BUNDLED_STYLES = {
    "apa": "apa.csl",
    "chicago-author-date": "chicago-author-date.csl",
    "mla": "modern-language-association.csl",
}


_CSL_LOCALES = {"en": "en-US", "fr": "fr-FR"}


class UnknownCitationStyle(Exception):
    """Raised by resolve_style when given neither a bundled short name
    nor an existing .csl file path."""


def _starter_config_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "starter_config"


def resolve_style(style_name_or_path: str) -> Path:
    bundled_filename = _BUNDLED_STYLES.get(style_name_or_path)
    if bundled_filename:
        return _starter_config_dir() / "csl_styles" / bundled_filename

    path = Path(style_name_or_path)
    if not path.is_file():
        raise UnknownCitationStyle(
            f"Unknown citation style: '{style_name_or_path}' "
            f"(expected one of {', '.join(_BUNDLED_STYLES)}, or a path to a .csl file)"
        )
    return path


class _MarkdownFormatter:
    """citeproc-py ships no Markdown formatter (only .plain/.html/.rst;
    .rst uses Sphinx role syntax, not real Markdown) — this mirrors the
    exact shape citeproc.formatter.html exposes, verified against its
    real source, swapping HTML tags for `*italic*`/`**bold**`."""

    @staticmethod
    def preformat(text):
        return str(text)

    class Italic(str):
        def __new__(cls, text):
            return super().__new__(cls, "*{}*".format(text))

    class Bold(str):
        def __new__(cls, text):
            return super().__new__(cls, "**{}**".format(text))

    Oblique = Italic
    Light = str
    Underline = str

    class Superscript(str):
        def __new__(cls, text):
            return super().__new__(cls, "^{}^".format(text))

    class Subscript(str):
        def __new__(cls, text):
            return super().__new__(cls, "~{}~".format(text))

    SmallCaps = str


def _for_citeproc(record: dict) -> dict:
    """citeproc-py doesn't know the `director` and `host` name roles, which
    are all a broadcast may have, and reads them as plain strings, so they
    are credited as the author, as `build._csl_authors_to_list` does. It
    also drops `event-title`, where Zotero can keep a paper's proceedings."""
    known = dict(record)
    credited = known.pop("director", None) or known.pop("host", None)
    known.pop("host", None)
    if credited and not (known.get("author") or known.get("editor")):
        known["author"] = credited
    if known.get("event-title") and not known.get("container-title"):
        known["container-title"] = known["event-title"]
    return known


def render_citations(records: list[dict], style_path: Path, language: str | None = None) -> list[str]:
    """Renders each CSL-JSON record in `records`, in the given order,
    as a formatted citation string. `records` must already be resolved
    (e.g. via `PublicationsHandler.resolve`) — callers are responsible
    for only passing records that exist. `language` picks the locale of
    the style's own terms ("and", "pp."), else the style's default."""
    if not records:
        return []

    records = [_for_citeproc(record) for record in records]
    # citeproc-py warns about every export field it doesn't use (citekeys,
    # Better BibTeX's own keys), once per record.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        bib_source = CiteProcJSON(records)
    style = CitationStylesStyle(str(style_path), locale=_CSL_LOCALES.get(language), validate=False)
    bibliography = CitationStylesBibliography(style, bib_source, _MarkdownFormatter)

    for record in records:
        citation = Citation([CitationItem(record["id"])])
        bibliography.register(citation)
        bibliography.cite(citation, lambda undefined_keys: None)

    return [str(item) for item in bibliography.bibliography()]

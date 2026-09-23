"""Renders CSL-JSON records (already resolved via
`handlers.publications.PublicationsHandler.resolve`) as formatted
citations via citeproc-py (see SPECS.md, "Citation formatting"). Core
layer: no prompting, no printing — the CLI `list --format citation`
command owns all output."""

from pathlib import Path

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle
from citeproc.source.json import CiteProcJSON

_BUNDLED_STYLES = {
    "apa": "apa.csl",
    "chicago-author-date": "chicago-author-date.csl",
    "mla": "modern-language-association.csl",
}


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


def render_citations(records: list[dict], style_path: Path) -> list[str]:
    """Renders each CSL-JSON record in `records`, in the given order,
    as a formatted citation string. `records` must already be resolved
    (e.g. via `PublicationsHandler.resolve`) — callers are responsible
    for only passing records that exist."""
    if not records:
        return []

    bib_source = CiteProcJSON(records)
    style = CitationStylesStyle(str(style_path), validate=False)
    bibliography = CitationStylesBibliography(style, bib_source, _MarkdownFormatter)

    for record in records:
        citation = Citation([CitationItem(record["id"])])
        bibliography.register(citation)
        bibliography.cite(citation, lambda undefined_keys: None)

    return [str(item) for item in bibliography.bibliography()]

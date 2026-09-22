"""Ties schema + vocab + labels + handlers + data together into
`parco lint` (see SPECS.md, "CLI" → "Validation"). Returns structured
`LintIssue`s — no printing here, per the core/interface split."""

from pathlib import Path

from .data import load_category_rows
from .handlers import load_handler
from .handlers.base import HandlerContext
from .labels import load_labels
from .schema import load_all_schemas
from .validation import LintIssue, validate_common
from .vocab import VocabError, load_vocab


class ConfigError(Exception):
    """Raised when `parco lint` can't run because of a data-repo
    misconfiguration (bad schema, missing vocab/labels file, unknown
    handler, etc.) rather than a real lint issue with the data itself."""


def run_lint(data_dir: Path, category_filter: str | None = None) -> list[LintIssue]:
    issues: list[LintIssue] = []

    try:
        schemas = load_all_schemas(data_dir / "categories")
        vocab = load_vocab(data_dir / "vocab.yaml")
        labels = load_labels(data_dir / "labels.csv")

        for entry in labels.missing_translations():
            issues.append(LintIssue(
                "labels", entry.id, entry.category,
                f"labels.csv id '{entry.id}' (category '{entry.category}') is missing a translation",
            ))

        for name, schema in schemas.items():
            if category_filter and name != category_filter:
                continue
            rows = load_category_rows(data_dir, name)
            handler = load_handler(schema, HandlerContext(data_dir=data_dir))
            for row in rows:
                issues.extend(validate_common(schema, row, vocab))
                issues.extend(handler.validate(row))
    except (VocabError, FileNotFoundError, KeyError) as exc:
        raise ConfigError(f"Config error: {exc}") from exc

    return issues

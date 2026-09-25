"""Ties schema + vocab + translations + handlers + data together into
`parco lint` (see SPECS.md, "CLI" → "Validation"). Returns structured
`LintIssue`s — no printing here, per the core/interface split."""

from pathlib import Path

from .data import load_category_rows
from .handlers import load_handler
from .handlers.base import HandlerContext
from .schema import CategorySchema, load_all_schemas
from .translations import TranslationsTable, load_translations, translations_csv_path
from .validation import LintIssue, validate_common
from .vocab import VocabError, load_vocab


class ConfigError(Exception):
    """Raised when `parco lint` can't run because of a data-repo
    misconfiguration (bad schema, missing vocab/translations file, unknown
    handler, etc.) rather than a real lint issue with the data itself."""


def _check_glossary_fields(
    schema: CategorySchema, row: dict, translations: TranslationsTable
) -> list[LintIssue]:
    """A `glossary: <category>` field (e.g. `city`) is a soft,
    non-blocking check: SPECS.md is explicit that an unmatched value
    never blocks entry — the glossary is an enhancement, not a
    requirement — so this always reports at "warning" severity, which
    never affects `parco lint`'s exit code."""
    issues = []
    for field in schema.fields:
        if not field.glossary:
            continue
        value = row.get(field.name)
        if value and not translations.exists(field.glossary, value):
            issues.append(LintIssue(
                schema.name, row.get("id"), field.name,
                f"'{value}' has no '{field.glossary}' glossary entry in translations.csv",
                severity="warning",
            ))
    return issues


def run_lint(data_dir: Path, category_filter: str | None = None) -> list[LintIssue]:
    issues: list[LintIssue] = []

    try:
        schemas = load_all_schemas(data_dir / "categories")
        vocab = load_vocab(data_dir / "vocab.yaml")
        translations = load_translations(translations_csv_path(data_dir))

        for entry in translations.missing_translations():
            issues.append(LintIssue(
                "translations", entry.id, entry.category,
                f"translations.csv id '{entry.id}' (category '{entry.category}') is missing a translation",
            ))

        for name, schema in schemas.items():
            if category_filter and name != category_filter:
                continue
            rows = load_category_rows(data_dir, name)
            handler = load_handler(schema, HandlerContext(data_dir=data_dir))
            for row in rows:
                issues.extend(validate_common(schema, row, vocab))
                issues.extend(handler.validate(row))
                issues.extend(_check_glossary_fields(schema, row, translations))
    except (VocabError, FileNotFoundError, KeyError) as exc:
        raise ConfigError(f"Config error: {exc}") from exc

    return issues

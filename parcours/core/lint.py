"""Ties schema + vocab + labels + handlers + data together into
`parco lint` (see SPECS.md, "CLI" → "Validation"). Returns structured
`LintIssue`s — no printing here, per the core/interface split."""

import importlib
from pathlib import Path

from .data import load_category_rows
from .handlers.base import HandlerContext
from .handlers.generic import GenericHandler
from .handlers.publications import PublicationsHandler
from .labels import load_labels
from .schema import CategorySchema, load_all_schemas
from .validation import LintIssue, validate_common
from .vocab import load_vocab

_BUILTIN_HANDLERS = {
    "generic": GenericHandler,
    "publications": PublicationsHandler,
}


def _load_handler(schema: CategorySchema, context: HandlerContext):
    handler_name = schema.handler
    if ":" in handler_name:
        module_name, class_name = handler_name.split(":")
        module = importlib.import_module(module_name)
        handler_cls = getattr(module, class_name)
    else:
        handler_cls = _BUILTIN_HANDLERS[handler_name]
    return handler_cls(schema, context)


def run_lint(data_dir: Path, category_filter: str | None = None) -> list[LintIssue]:
    issues: list[LintIssue] = []

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
        handler = _load_handler(schema, HandlerContext(data_dir=data_dir))
        for row in rows:
            issues.extend(validate_common(schema, row, vocab))
            issues.extend(handler.validate(row))

    return issues

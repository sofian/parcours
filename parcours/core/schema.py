"""Loads a category's `categories/<name>.yaml` schema file (see SPECS.md,
"Category schemas (drafts)")."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _conditions_hold(conditions: dict[str, str], entry: dict) -> bool:
    return all(
        (entry.get(name) or "").strip().lower() == str(value).strip().lower()
        for name, value in conditions.items()
    )


@dataclass
class FieldSpec:
    name: str
    type: str = "string"
    required: bool = False
    vocab: str | None = None
    default: Any = None
    generated: bool = False
    precision: str | None = None
    glossary: str | None = None
    # `required_unless: {status: in-progress}` — `required` is waived when
    # every listed field holds the listed value (e.g. an artwork still in
    # progress has no production year yet).
    required_unless: dict[str, str] | None = None
    # `skip_when: {type: affiliation}` — the field doesn't apply when every
    # listed field holds the listed value (e.g. an affiliation has no
    # full-time/part-time status), so it stays blank.
    skip_when: dict[str, str] | None = None

    def is_required(self, entry: dict) -> bool:
        if not self.required:
            return False
        if self.required_unless and _conditions_hold(self.required_unless, entry):
            return False
        return True

    def is_skipped(self, entry: dict) -> bool:
        return bool(self.skip_when) and _conditions_hold(self.skip_when, entry)


@dataclass
class DedupRule:
    conditions: list[dict]
    outcome: str


@dataclass
class CategorySchema:
    name: str
    handler: str = "generic"
    fields: list[FieldSpec] = field(default_factory=list)
    options: dict = field(default_factory=dict)
    dedup: list[DedupRule] = field(default_factory=list)
    require_one_of: list[list[str]] = field(default_factory=list)

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def get_field(self, name: str) -> FieldSpec | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def default_date_field(self) -> str | None:
        """The field `--by year`/`--after`/`--before` treat as this
        category's one designated date — `start_date` if present (a
        range's beginning), else plain `date` (a single point in time),
        else None. The same convention `core/init.py`'s generated
        `order_by` already uses."""
        field_names = self.field_names()
        if "start_date" in field_names:
            return "start_date"
        if "date" in field_names:
            return "date"
        return None


def load_category_schema(path: Path) -> CategorySchema:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    fields = [FieldSpec(**f) for f in raw.get("fields", [])]
    dedup = [
        DedupRule(conditions=rule["when"], outcome=rule["as"])
        for rule in raw.get("dedup", [])
    ]
    return CategorySchema(
        name=raw["name"],
        handler=raw.get("handler", "generic"),
        fields=fields,
        options=raw.get("options", {}),
        dedup=dedup,
        require_one_of=raw.get("require_one_of", []),
    )


def load_all_schemas(categories_dir: Path) -> dict[str, CategorySchema]:
    schemas = {}
    for path in sorted(categories_dir.glob("*.yaml")):
        schema = load_category_schema(path)
        schemas[schema.name] = schema
    return schemas

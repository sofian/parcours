"""Loads a category's `categories/<name>.yaml` schema file (see SPECS.md,
"Category schemas (drafts)")."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FieldSpec:
    name: str
    type: str = "string"
    required: bool = False
    vocab: str | None = None
    default: Any = None
    generated: bool = False
    precision: str | None = None


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

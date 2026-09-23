"""Loads `views.yaml`: the category → RenderCV entry-type field mapping
(see SPECS.md, "views.yaml (draft)")."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ViewSpec:
    name: str
    source: str
    entry_type: str
    fields: dict[str, Any] = field(default_factory=dict)
    group_by: str | None = None


def load_views(path: Path) -> dict[str, ViewSpec]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    views = {}
    for name, view_raw in raw.items():
        views[name] = ViewSpec(
            name=name,
            source=view_raw["source"],
            entry_type=view_raw["entry_type"],
            fields=view_raw.get("fields", {}),
            group_by=view_raw.get("group_by"),
        )
    return views

"""The handler interface every category's behavior plugs into (see
SPECS.md, "Category handlers" and its "Handler interface (draft)")."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class Match:
    existing_row_id: str
    kind: str  # "duplicate" | "related"
    reason: str


@dataclass
class HandlerContext:
    data_dir: Path


class CategoryHandler(ABC):
    """Generic behavior by default; a schema's `handler:` module provides
    a subclass for anything category-specific."""

    def __init__(self, schema, context: HandlerContext):
        self.schema = schema
        self.context = context

    def validate(self, entry: dict) -> list:
        """Handler-specific validation, beyond the common
        required/vocab/require_one_of/precision checks every category
        already gets from `core.validation.validate_common`."""
        return []

    def setup_warnings(self) -> list[str]:
        """One-time, repo-wide configuration problems (e.g. a citation
        export file that doesn't exist) — distinct from per-entry
        `validate()` issues. Surfaced once by `parco import`/`lint`
        callers instead of manifesting as a wall of identical per-row
        failures with no obvious common cause."""
        return []

    @abstractmethod
    def find_matches(self, entry: dict, existing: list[dict]) -> list[Match]:
        """Check `entry` against `existing` rows per the schema's own
        `dedup:` rules (or handler-specific logic, e.g. `publications`)."""


@runtime_checkable
class Citable(Protocol):
    def citation(self, key: str, style: str, lang: str) -> str: ...


@runtime_checkable
class Importable(Protocol):
    def plan_import(self, source, options): ...

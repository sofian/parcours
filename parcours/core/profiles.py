"""Loads `profiles/*.yaml`: one CV variant/language combination, with an
optional `extends` merge against a shared base file (see SPECS.md,
"Profiles"). A single, shallow merge level — no chained `extends`, no
per-section deep merge."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .templating import resolve_template

_DEFAULT_OUTPUT_TEMPLATE = "cv-{name}-{language}"


@dataclass
class Profile:
    meta: dict[str, Any]
    sections: list[dict] = field(default_factory=list)

    @property
    def output(self) -> str:
        template = self.meta.get("output", _DEFAULT_OUTPUT_TEMPLATE)
        # If template has no placeholders, return as-is; otherwise interpolate
        if isinstance(template, str) and "{" not in template:
            return template
        return resolve_template(template, self.meta, self.meta["language"])


def _load_raw(profiles_dir: Path, name: str) -> dict:
    with open(profiles_dir / f"{name}.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_profile(profiles_dir: Path, name: str) -> Profile:
    raw = _load_raw(profiles_dir, name)

    base_name = raw.get("extends")
    if base_name:
        base = _load_raw(profiles_dir, base_name)
        merged = {**base, **raw}
        merged["meta"] = {**base.get("meta", {}), **raw.get("meta", {})}
    else:
        merged = raw

    return Profile(
        meta=merged.get("meta", {}),
        sections=merged.get("sections", []),
    )

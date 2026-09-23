"""Loads `identity.yaml`: the singleton (not a CSV category) config
holding what every CV needs regardless of section content — name,
contact info, and audience-specific variants (see SPECS.md, "Identity /
personal-info config")."""

from pathlib import Path

import yaml

from .templating import resolve_field


class IdentityVariantNotFound(Exception):
    """Raised when a profile names an `identity_variant` that doesn't
    exist in identity.yaml."""


def load_identity(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_identity(identity: dict, variant_name: str, language: str) -> dict:
    variants = identity.get("variants", {})
    if variant_name not in variants:
        raise IdentityVariantNotFound(f"No identity variant '{variant_name}' in identity.yaml")
    variant_fields = variants[variant_name]

    name = identity.get("name", {})
    full_name = " ".join(part for part in [name.get("first"), name.get("last")] if part)

    cv = {"name": full_name}

    headline = resolve_field(variant_fields, "title", language)
    if headline:
        cv["headline"] = headline

    for source_key, cv_key in [("email", "email"), ("phone", "phone"), ("homepage", "website")]:
        value = variant_fields.get(source_key)
        if value:
            cv[cv_key] = value

    return cv

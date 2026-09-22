"""Loads and checks values against `vocab.yaml` (see SPECS.md, "vocab.yaml
(draft)")."""

from pathlib import Path

import yaml


class VocabError(Exception):
    """Raised for a malformed vocab.yaml or a reference to an unknown list."""


def load_vocab(path: Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    for key, values in raw.items():
        if not isinstance(values, list):
            raise VocabError(
                f"vocab.yaml entry '{key}' must be a list, got {type(values).__name__}"
            )
    return raw


def is_valid_value(vocab: dict[str, list[str]], vocab_name: str, value: str) -> bool:
    if vocab_name not in vocab:
        raise VocabError(f"Unknown vocab list: '{vocab_name}'")
    return value in vocab[vocab_name]

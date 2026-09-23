"""Scaffolds a brand-new parco data repo (see SPECS.md, "CLI" -> "Init").
Core layer: no prompting here — the CLI `init` command owns all wizard
interaction and calls scaffold_repo with the answers it collected. The
one sanctioned exception to "core never shells out interactively" is the
`git init`/`git add`/`git commit` sequence at the end, matching the same
precedent as core/build.py's `rendercv` invocation."""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .schema import CategorySchema, load_all_schemas, load_category_schema
from .views import load_views


class RepoAlreadyExists(Exception):
    """Raised by scaffold_repo when `path/parco.yaml` already exists —
    init is fresh-repo-only in this first cut, never "add missing
    pieces" to an existing one."""


class GitInitFailed(Exception):
    """Raised when `git init`/`git add`/`git commit` fails while
    scaffolding a new repo."""


class GitIdentityMissing(Exception):
    """Raised when git can't resolve an author identity (no
    user.name/user.email configured, and auto-detection fails).
    Checked before any file is written, so a doomed `git commit` at the
    very end never leaves a half-scaffolded, uncommitted repo behind."""


def check_git_identity_configured() -> None:
    """Raises GitIdentityMissing if `git commit` would fail for lack of
    an author identity — the same resolution `git commit` itself uses
    (env vars, then local/global/system config, then auto-detection),
    checked via `git var` so this never diverges from what a real
    commit would actually do."""
    try:
        subprocess.run(["git", "var", "GIT_AUTHOR_IDENT"], check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        raise GitIdentityMissing(
            "Git author identity isn't configured, so the final commit would fail. Run:\n"
            '  git config --global user.email "you@example.com"\n'
            '  git config --global user.name "Your Name"\n'
            f"then try again.\n\n{stderr}"
        ) from exc


@dataclass
class InitAnswers:
    first_name: str
    last_name: str
    variant_name: str
    languages: list[str]
    currency: str
    title_en: str = ""
    title_fr: str = ""
    email: str = ""
    phone: str = ""
    homepage: str = ""


def _starter_config_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "starter_config"


def _write_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)


def _write_parco_yaml(path: Path, answers: InitAnswers) -> None:
    _write_yaml(path / "parco.yaml", {
        "currency": {"default": answers.currency, "report": answers.currency},
    })


def _copy_categories_and_csvs(path: Path, starter_dir: Path) -> None:
    categories_dir = path / "categories"
    categories_dir.mkdir(parents=True, exist_ok=True)
    for schema_path in sorted((starter_dir / "categories").glob("*.yaml")):
        dest = categories_dir / schema_path.name
        shutil.copy2(schema_path, dest)
        schema = load_category_schema(dest)
        csv_path = path / f"{schema.name}.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(",".join(schema.field_names()) + "\n")


def _write_identity_yaml(path: Path, answers: InitAnswers) -> None:
    variant: dict[str, str] = {}
    for key, value in [
        ("title_en", answers.title_en),
        ("title_fr", answers.title_fr),
        ("email", answers.email),
        ("phone", answers.phone),
        ("homepage", answers.homepage),
    ]:
        if value:
            variant[key] = value

    _write_yaml(path / "identity.yaml", {
        "name": {"first": answers.first_name, "last": answers.last_name},
        "variants": {answers.variant_name: variant},
    })


def _section_order_by(schema: CategorySchema) -> str | None:
    field_names = schema.field_names()
    if "start_date" in field_names:
        return "start_date desc"
    if "date" in field_names:
        return "date desc"
    return None


def _build_sections(path: Path) -> list[dict]:
    views = load_views(path / "views.yaml")
    schemas = load_all_schemas(path / "categories")

    sections = []
    for view_name, view in views.items():
        section: dict = {"id": view_name, "source": view_name}
        schema = schemas.get(view.source)
        if schema is not None:
            order_by = _section_order_by(schema)
            if order_by:
                section["order_by"] = order_by
        sections.append(section)
    return sections


def _write_profiles(path: Path, answers: InitAnswers) -> None:
    profiles_dir = path / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    sections = _build_sections(path)

    if len(answers.languages) == 1:
        language = answers.languages[0]
        profile = {
            "meta": {
                "name": answers.variant_name,
                "language": language,
                "format": "pdf",
                "theme": "sb2nov",
                "identity_variant": answers.variant_name,
            },
            "sections": sections,
        }
        _write_yaml(profiles_dir / f"{answers.variant_name}-{language}.yaml", profile)
        return

    base_name = f"_{answers.variant_name}"
    base = {
        "meta": {
            "name": answers.variant_name,
            "format": "pdf",
            "theme": "sb2nov",
            "identity_variant": answers.variant_name,
        },
        "sections": sections,
    }
    _write_yaml(profiles_dir / f"{base_name}.yaml", base)
    for language in answers.languages:
        child = {"extends": base_name, "meta": {"language": language}}
        _write_yaml(profiles_dir / f"{answers.variant_name}-{language}.yaml", child)


def _git_init_and_commit(path: Path) -> None:
    try:
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initialized parco data repo"],
            cwd=path, check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        raise GitInitFailed(f"git init failed: {stderr}") from exc


def scaffold_repo(path: Path, answers: InitAnswers) -> None:
    """Scaffolds a brand-new parco data repo at `path` and commits it.
    Raises RepoAlreadyExists (writing nothing) if `path/parco.yaml`
    already exists, GitIdentityMissing (writing nothing) if git can't
    resolve an author identity, or GitInitFailed if the final git
    init/commit fails for some other reason."""
    path = Path(path)
    if (path / "parco.yaml").is_file():
        raise RepoAlreadyExists(f"A parco data repo already exists at {path}")

    check_git_identity_configured()

    path.mkdir(parents=True, exist_ok=True)
    starter_dir = _starter_config_dir()

    _write_parco_yaml(path, answers)
    _copy_categories_and_csvs(path, starter_dir)
    shutil.copy2(starter_dir / "vocab.yaml", path / "vocab.yaml")
    shutil.copy2(starter_dir / "translations.csv", path / "translations.csv")
    shutil.copy2(starter_dir / "views.yaml", path / "views.yaml")
    _write_identity_yaml(path, answers)
    _write_profiles(path, answers)
    _git_init_and_commit(path)

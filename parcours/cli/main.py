"""The Typer app — thin, owns all prompts/printing (see SPECS.md, "Code
architecture: modular core + thin interfaces")."""

import typer

from ..core.lint import ConfigError, run_lint
from ..core.repo import DataRepoNotFound, find_data_repo

app = typer.Typer()


@app.callback()
def main():
    """Parcours: a personal, git-tracked academic/artistic CV data system."""


@app.command()
def lint(category: str = typer.Argument(None, help="Only lint this category")):
    """Check category data against its schema, vocab, and labels."""
    try:
        data_dir = find_data_repo()
    except DataRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    try:
        issues = run_lint(data_dir, category_filter=category)
    except ConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    if not issues:
        typer.echo("No lint issues found.")
        raise typer.Exit(code=0)

    for issue in issues:
        location = issue.category
        if issue.row_id:
            location += f"[{issue.row_id}]"
        if issue.field:
            location += f".{issue.field}"
        typer.echo(f"{issue.severity.upper()}: {location}: {issue.message}")

    error_count = sum(1 for i in issues if i.severity == "error")
    raise typer.Exit(code=1 if error_count else 0)


if __name__ == "__main__":
    app()

from datetime import date

import pytest
import typer

from parcours.cli import wizard
from parcours.core.schema import CategorySchema, FieldSpec


def _prompt_sequence(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr(wizard.typer, "prompt", lambda *a, **k: next(it))
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)


def _schema():
    return CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="title_en", required=True),
            FieldSpec(name="status", vocab="widget_status"),
        ],
    )


def test_skips_generated_fields(monkeypatch):
    _prompt_sequence(monkeypatch, ["A Widget", "1"])
    values = wizard.collect_field_values(_schema(), {"widget_status": ["draft", "published"]})
    assert "id" not in values


def test_plain_field_collects_typed_value(monkeypatch):
    _prompt_sequence(monkeypatch, ["A Widget", "1"])
    values = wizard.collect_field_values(_schema(), {"widget_status": ["draft", "published"]})
    assert values["title_en"] == "A Widget"


def test_required_plain_field_reprompts_on_blank(monkeypatch):
    _prompt_sequence(monkeypatch, ["", "A Widget", "1"])
    values = wizard.collect_field_values(_schema(), {"widget_status": ["draft", "published"]})
    assert values["title_en"] == "A Widget"


def test_vocab_field_picks_by_number(monkeypatch):
    _prompt_sequence(monkeypatch, ["A Widget", "2"])
    values = wizard.collect_field_values(_schema(), {"widget_status": ["draft", "published"]})
    assert values["status"] == "published"


def test_vocab_field_preselects_the_schemas_declared_default_when_no_prefill(monkeypatch):
    calls = []

    def _fake_prompt(*args, **kwargs):
        calls.append(kwargs)
        return kwargs.get("default")  # simulate pressing Enter to accept the default

    monkeypatch.setattr(wizard.typer, "prompt", _fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)

    schema = CategorySchema(
        name="artworks",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="role", vocab="artwork_role", required=True, default="author"),
        ],
    )

    values = wizard.collect_field_values(schema, {"artwork_role": ["author", "collaborator"]})

    assert values["role"] == "author"
    assert calls[0]["default"] == 1  # "author" is choice #1


def test_vocab_field_prefill_wins_over_the_schemas_declared_default(monkeypatch):
    calls = []

    def _fake_prompt(*args, **kwargs):
        calls.append(kwargs)
        return kwargs.get("default")  # simulate pressing Enter to accept the shown default

    monkeypatch.setattr(wizard.typer, "prompt", _fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)

    schema = CategorySchema(
        name="artworks",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="role", vocab="artwork_role", required=True, default="author"),
        ],
    )

    # existing row's value is "collaborator" (e.g. via `edit`) — this must
    # win over the schema's own static "author" default.
    values = wizard.collect_field_values(
        schema, {"artwork_role": ["author", "collaborator"]}, prefill={"role": "collaborator"}
    )

    assert values["role"] == "collaborator"
    assert calls[0]["default"] == 2  # "collaborator" is choice #2, not the schema default's #1


def test_optional_vocab_field_can_be_skipped(monkeypatch):
    schema = CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="status", vocab="widget_status", required=False),
        ],
    )
    _prompt_sequence(monkeypatch, ["0"])
    values = wizard.collect_field_values(schema, {"widget_status": ["draft", "published"]})
    assert values["status"] == ""


def test_require_one_of_group_reprompts_when_all_blank(monkeypatch):
    schema = CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="title_en", required=False),
            FieldSpec(name="title_fr", required=False),
        ],
        require_one_of=[["title_en", "title_fr"]],
    )
    _prompt_sequence(monkeypatch, ["", "", "A Widget", ""])
    values = wizard.collect_field_values(schema, {})
    assert values["title_en"] == "A Widget"
    assert values["title_fr"] == ""


def test_prefill_becomes_the_shown_default(monkeypatch):
    calls = []

    def fake_prompt(text, default="", show_default=True):
        calls.append(default)
        return default or "typed"

    monkeypatch.setattr(wizard.typer, "prompt", fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)

    schema = CategorySchema(
        name="widgets",
        fields=[FieldSpec(name="id", generated=True), FieldSpec(name="title_en", required=True)],
    )
    values = wizard.collect_field_values(schema, {}, prefill={"title_en": "Existing Title"})

    assert calls == ["Existing Title"]
    assert values["title_en"] == "Existing Title"


def test_search_rows_matches_substring_case_insensitively():
    rows = [
        {"id": "abc123", "title_en": "Machine Learning Art"},
        {"id": "def456", "title_en": "Completely Unrelated"},
    ]
    matches = wizard.search_rows(rows, "machine")
    assert [m["id"] for m in matches] == ["abc123"]


def test_search_rows_matches_across_any_field():
    rows = [
        {"id": "abc123", "title_en": "A Widget", "status": "draft"},
        {"id": "def456", "title_en": "B Widget", "status": "published"},
    ]
    matches = wizard.search_rows(rows, "published")
    assert [m["id"] for m in matches] == ["def456"]


def test_search_rows_skips_comments():
    rows = [
        {"id": "abc123", "title_en": "A Widget", "comment": "check the vernissage date"},
        {"id": "def456", "title_en": "Vernissage", "comment": ""},
    ]
    matches = wizard.search_rows(rows, "vernissage")
    assert [m["id"] for m in matches] == ["def456"]


def test_pick_row_returns_none_for_no_matches(monkeypatch):
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)
    assert wizard.pick_row(_schema(), []) is None


def test_pick_row_returns_the_chosen_row(monkeypatch):
    rows = [{"id": "abc123", "title_en": "A"}, {"id": "def456", "title_en": "B"}]
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)
    monkeypatch.setattr(wizard.typer, "prompt", lambda *a, **k: "2")

    picked = wizard.pick_row(_schema(), rows)

    assert picked["id"] == "def456"


def test_pick_row_returns_none_when_cancelled(monkeypatch):
    rows = [{"id": "abc123", "title_en": "A"}]
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)
    monkeypatch.setattr(wizard.typer, "prompt", lambda *a, **k: "")

    assert wizard.pick_row(_schema(), rows) is None


def test_optional_date_field_with_no_prefill_defaults_to_blank_on_skip(monkeypatch):
    calls = []

    def fake_prompt(text, default="", show_default=True):
        calls.append(default)
        return default

    monkeypatch.setattr(wizard.typer, "prompt", fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)

    schema = CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="end_date", type="date", required=False),
        ],
    )
    values = wizard.collect_field_values(schema, {})

    assert calls == [""]
    assert values["end_date"] == ""


def test_required_date_field_with_no_prefill_defaults_to_current_year(monkeypatch):
    calls = []

    def fake_prompt(text, default="", show_default=True):
        calls.append(default)
        return default

    monkeypatch.setattr(wizard.typer, "prompt", fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)

    schema = CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="start_date", type="date", required=True),
        ],
    )
    values = wizard.collect_field_values(schema, {})

    current_year = str(date.today().year)
    assert calls == [current_year]
    assert values["start_date"] == current_year


def test_required_vocab_field_with_missing_vocab_list_raises_instead_of_looping(monkeypatch):
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)

    schema = CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="status", vocab="undefined_status", required=True),
        ],
    )

    with pytest.raises(typer.BadParameter):
        wizard.collect_field_values(schema, {})


def test_weight_is_always_asked_last_regardless_of_declared_position(monkeypatch):
    prompted_fields = []

    def fake_prompt(text, default="", show_default=True):
        prompted_fields.append(text.split(" ")[0].split("(")[0])
        return ""

    monkeypatch.setattr(wizard.typer, "prompt", fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)

    schema = CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="weight", type="int"),
            FieldSpec(name="title_en"),
            FieldSpec(name="event"),
        ],
    )
    wizard.collect_field_values(schema, {})

    assert prompted_fields == ["title_en", "event", "weight"]


def test_comment_is_asked_after_weight(monkeypatch):
    prompted_fields = []

    def fake_prompt(text, default="", show_default=True):
        prompted_fields.append(text.split(" ")[0].split("(")[0])
        return ""

    monkeypatch.setattr(wizard.typer, "prompt", fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)

    schema = CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="weight", type="int"),
            FieldSpec(name="comment", type="text"),
            FieldSpec(name="title_en"),
        ],
    )
    wizard.collect_field_values(schema, {})

    assert prompted_fields == ["title_en", "weight", "comment"]


def _conditional_schema():
    return CategorySchema(
        name="artworks",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="status", vocab="artwork_status"),
            FieldSpec(name="date", type="date", required=True, required_unless={"status": "in-progress"}),
        ],
    )


def test_required_unless_lets_the_wizard_skip_the_field_when_the_condition_holds(monkeypatch):
    _prompt_sequence(monkeypatch, ["1", ""])
    values = wizard.collect_field_values(_conditional_schema(), {"artwork_status": ["in-progress", "completed"]})
    assert values == {"status": "in-progress", "date": ""}


def test_required_unless_keeps_the_field_required_otherwise(monkeypatch):
    _prompt_sequence(monkeypatch, ["2", "", "2024"])
    values = wizard.collect_field_values(_conditional_schema(), {"artwork_status": ["in-progress", "completed"]})
    assert values == {"status": "completed", "date": "2024"}


def _skip_when_schema():
    return CategorySchema(
        name="positions",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="type", vocab="position_type"),
            FieldSpec(name="position_status", vocab="position_status", skip_when={"type": "affiliation"}),
            FieldSpec(name="start_date", type="date", precision="year"),
        ],
    )


POSITION_VOCAB = {
    "position_type": ["academic", "affiliation"],
    "position_status": ["full-time", "part-time"],
}


def test_skip_when_does_not_prompt_for_the_field(monkeypatch):
    _prompt_sequence(monkeypatch, ["2", "2020"])
    values = wizard.collect_field_values(_skip_when_schema(), POSITION_VOCAB)
    assert values == {"type": "affiliation", "position_status": "", "start_date": "2020"}


def test_skip_when_still_prompts_when_the_condition_does_not_hold(monkeypatch):
    _prompt_sequence(monkeypatch, ["1", "1", "2020"])
    values = wizard.collect_field_values(_skip_when_schema(), POSITION_VOCAB)
    assert values == {"type": "academic", "position_status": "full-time", "start_date": "2020"}


def test_skip_when_clears_a_stale_value_when_an_edit_changes_the_condition(monkeypatch):
    _prompt_sequence(monkeypatch, ["2", "2020"])
    prefill = {"type": "academic", "position_status": "full-time", "start_date": "2020"}
    values = wizard.collect_field_values(_skip_when_schema(), POSITION_VOCAB, prefill=prefill)
    assert values == {"type": "affiliation", "position_status": "", "start_date": "2020"}


def test_date_field_prompt_shows_the_format_and_rejects_bad_input(monkeypatch):
    prompts, echoes = [], []
    answers = iter(["06-09-18", "2018", "2018-09"])

    def _fake_prompt(text, **kwargs):
        prompts.append(text)
        return next(answers)

    monkeypatch.setattr(wizard.typer, "prompt", _fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda msg="", **k: echoes.append(msg))
    schema = CategorySchema(name="grants", fields=[
        FieldSpec(name="start_date", type="date", precision="month", required=True),
    ])

    value = wizard.ask_field_by_name(schema, {}, "start_date", "2018")

    assert value == "2018-09"
    assert "YYYY-MM or YYYY-MM-DD" in prompts[0]
    assert len(prompts) == 3
    assert any("YYYY-MM" in e for e in echoes)


def test_required_date_default_matches_the_precision_floor(monkeypatch):
    calls = []

    def _fake_prompt(text, **kwargs):
        calls.append(kwargs.get("default"))
        return kwargs.get("default")

    monkeypatch.setattr(wizard.typer, "prompt", _fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)
    schema = CategorySchema(name="grants", fields=[
        FieldSpec(name="id", generated=True),
        FieldSpec(name="start_date", type="date", precision="month", required=True),
    ])
    values = wizard.collect_field_values(schema, {})
    assert values["start_date"] == date.today().strftime("%Y-%m")

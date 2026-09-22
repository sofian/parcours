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

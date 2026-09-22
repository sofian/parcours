from parcours.core.schema import CategorySchema, FieldSpec
from parcours.core.validation import validate_common


def _schema(**overrides):
    defaults = dict(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="title_en"),
            FieldSpec(name="title_fr"),
            FieldSpec(name="status", required=True, vocab="widget_status"),
            FieldSpec(name="start_date", type="date", precision="month", required=True),
        ],
        require_one_of=[["title_en", "title_fr"]],
    )
    defaults.update(overrides)
    return CategorySchema(**defaults)


VOCAB = {"widget_status": ["draft", "published"]}


def test_passes_a_fully_valid_entry():
    entry = {
        "id": "widget-1", "title_en": "A Widget", "title_fr": "",
        "status": "draft", "start_date": "2024-09",
    }
    assert validate_common(_schema(), entry, VOCAB) == []


def test_flags_missing_required_field():
    entry = {"id": "widget-1", "title_en": "A Widget", "status": "", "start_date": "2024-09"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field == "status" and i.severity == "error" for i in issues)


def test_flags_invalid_vocab_value():
    entry = {
        "id": "widget-1", "title_en": "A Widget",
        "status": "not-a-real-status", "start_date": "2024-09",
    }
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field == "status" for i in issues)


def test_flags_missing_require_one_of_group():
    entry = {"id": "widget-1", "title_en": "", "title_fr": "", "status": "draft", "start_date": "2024-09"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field is None and "title_en" in i.message for i in issues)


def test_require_one_of_passes_with_only_one_filled():
    entry = {"id": "widget-1", "title_en": "", "title_fr": "Un Widget", "status": "draft", "start_date": "2024-09"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert issues == []


def test_flags_date_below_precision_floor():
    entry = {"id": "widget-1", "title_en": "A Widget", "status": "draft", "start_date": "2024"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field == "start_date" for i in issues)


def test_flags_unparseable_date():
    entry = {"id": "widget-1", "title_en": "A Widget", "status": "draft", "start_date": "not-a-date"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field == "start_date" for i in issues)


def test_generated_fields_are_never_flagged_as_missing():
    entry = {"id": "", "title_en": "A Widget", "status": "draft", "start_date": "2024-09"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert not any(i.field == "id" for i in issues)

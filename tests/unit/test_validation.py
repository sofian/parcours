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
            FieldSpec(name="co_authors", type="person_list"),
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


def test_passes_a_valid_person_list():
    entry = {
        "id": "widget-1", "title_en": "A Widget", "status": "draft",
        "start_date": "2024-09", "co_authors": "Gagné, Rosalie D.; Montenegro, Etienne",
    }
    assert validate_common(_schema(), entry, VOCAB) == []


def test_flags_a_malformed_person_list():
    entry = {
        "id": "widget-1", "title_en": "A Widget", "status": "draft",
        "start_date": "2024-09", "co_authors": "Rosalie Gagné",  # missing the comma
    }
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field == "co_authors" for i in issues)


def test_generated_fields_are_never_flagged_as_missing():
    entry = {"id": "", "title_en": "A Widget", "status": "draft", "start_date": "2024-09"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert not any(i.field == "id" for i in issues)


def _conditional_schema():
    return CategorySchema(
        name="artworks",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="status", vocab="artwork_status"),
            FieldSpec(name="date", type="date", precision="year", required=True,
                      required_unless={"status": "in-progress"}),
        ],
    )


ART_VOCAB = {"artwork_status": ["in-progress", "completed"]}


def test_required_unless_exempts_a_blank_field_when_the_condition_holds():
    entry = {"id": "a1", "status": "in-progress", "date": ""}
    assert validate_common(_conditional_schema(), entry, ART_VOCAB) == []


def test_required_unless_still_requires_the_field_otherwise():
    for status in ("completed", ""):
        entry = {"id": "a1", "status": status, "date": ""}
        issues = validate_common(_conditional_schema(), entry, ART_VOCAB)
        assert [i.field for i in issues] == ["date"]


def test_required_unless_still_validates_a_value_that_is_given():
    entry = {"id": "a1", "status": "in-progress", "date": "someday"}
    issues = validate_common(_conditional_schema(), entry, ART_VOCAB)
    assert [i.field for i in issues] == ["date"]


def _skip_when_schema():
    return CategorySchema(
        name="positions",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="type", vocab="position_type"),
            FieldSpec(name="position_status", vocab="position_status", required=True,
                      skip_when={"type": "affiliation"}),
        ],
    )


POSITION_VOCAB = {
    "position_type": ["academic", "affiliation"],
    "position_status": ["full-time", "part-time"],
}


def test_skip_when_flags_a_value_on_a_row_the_field_does_not_apply_to():
    entry = {"id": "p1", "type": "affiliation", "position_status": "full-time"}
    issues = validate_common(_skip_when_schema(), entry, POSITION_VOCAB)
    assert [i.field for i in issues] == ["position_status"]
    assert "does not apply" in issues[0].message


def test_skip_when_waives_required_when_the_condition_holds():
    entry = {"id": "p1", "type": "affiliation", "position_status": ""}
    assert validate_common(_skip_when_schema(), entry, POSITION_VOCAB) == []


def test_skip_when_leaves_other_rows_alone():
    entry = {"id": "p1", "type": "academic", "position_status": "full-time"}
    assert validate_common(_skip_when_schema(), entry, POSITION_VOCAB) == []


def _range_schema(**overrides):
    fields = [
        FieldSpec(name="id", generated=True),
        FieldSpec(name="start_date", type="date", precision="year"),
        FieldSpec(name="end_date", type="date", precision="year"),
    ]
    return _schema(fields=fields, require_one_of=[], **overrides)


def _range_issues(start, end):
    entry = {"id": "widget-1", "start_date": start, "end_date": end}
    return validate_common(_range_schema(), entry, VOCAB)


def test_flags_an_end_date_before_the_start_date():
    issues = _range_issues("2013-09", "2013-08")
    assert [i.field for i in issues] == ["end_date"]
    assert "2013-08" in issues[0].message and "2013-09" in issues[0].message
    assert issues[0].severity == "error"


def test_a_range_within_one_month_passes():
    assert _range_issues("2013-09", "2013-09") == []


def test_a_blank_end_date_is_ongoing_and_passes():
    assert _range_issues("2013-09", "") == []


def test_flags_a_coarser_end_date_that_would_render_before_the_start():
    # `2013` reads as 2013-01-01 at render time, so RenderCV rejects this.
    assert [i.field for i in _range_issues("2013-09", "2013")] == ["end_date"]


def test_a_malformed_range_date_is_only_flagged_as_malformed():
    issues = _range_issues("2013-09", "not-a-date")
    assert len(issues) == 1
    assert "not a valid date" in issues[0].message


def test_flags_an_end_date_before_a_plain_date_field():
    schema = _schema(fields=[
        FieldSpec(name="id", generated=True),
        FieldSpec(name="date", type="date", precision="year"),
        FieldSpec(name="end_date", type="date", precision="year"),
    ], require_one_of=[])
    issues = validate_common(schema, {"id": "w", "date": "2020", "end_date": "2019"}, VOCAB)
    assert [i.field for i in issues] == ["end_date"]


def test_each_prefixed_date_range_is_checked_separately():
    schema = _schema(fields=[
        FieldSpec(name="id", generated=True),
        FieldSpec(name="degree_start_date", type="date", precision="year"),
        FieldSpec(name="degree_end_date", type="date", precision="year"),
        FieldSpec(name="supervision_start_date", type="date", precision="year"),
        FieldSpec(name="supervision_end_date", type="date", precision="year"),
    ], require_one_of=[])
    entry = {
        "id": "w", "degree_start_date": "2020", "degree_end_date": "2021",
        "supervision_start_date": "2020", "supervision_end_date": "2019",
    }
    assert [i.field for i in validate_common(schema, entry, VOCAB)] == ["supervision_end_date"]

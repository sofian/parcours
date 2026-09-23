import pytest

from parcours.core.schema import CategorySchema, FieldSpec
from parcours.core.stats import UnknownStatsField, aggregate_counts


def _schema():
    return CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="status", required=True),
            FieldSpec(name="start_date", type="date"),
        ],
    )


def test_aggregates_by_a_plain_field():
    rows = [
        {"status": "draft"}, {"status": "published"}, {"status": "published"},
    ]

    counts = aggregate_counts(_schema(), rows, "status")

    assert counts == [("draft", 1), ("published", 2)]


def test_aggregates_blank_values_under_a_labeled_group():
    rows = [{"status": "draft"}, {"status": ""}]

    counts = aggregate_counts(_schema(), rows, "status")

    assert ("(blank)", 1) in counts


def test_aggregates_by_year_extracted_from_the_date_field():
    rows = [
        {"start_date": "2024-01"}, {"start_date": "2024-09"}, {"start_date": "2020"},
    ]

    counts = aggregate_counts(_schema(), rows, "year")

    assert counts == [("2020", 1), ("2024", 2)]


def test_by_year_ignores_unparseable_dates_rather_than_crashing():
    rows = [{"start_date": "2024-01"}, {"start_date": "not-a-date"}, {"start_date": ""}]

    counts = aggregate_counts(_schema(), rows, "year")

    assert counts == [("2024", 1)]


def test_by_year_raises_when_category_has_no_date_field():
    schema = CategorySchema(name="skills", fields=[FieldSpec(name="name")])

    with pytest.raises(UnknownStatsField):
        aggregate_counts(schema, [{"name": "Python"}], "year")


def test_unknown_field_raises():
    with pytest.raises(UnknownStatsField):
        aggregate_counts(_schema(), [{"status": "draft"}], "nonexistent")


def test_results_are_sorted_by_group_value():
    rows = [{"status": "published"}, {"status": "draft"}, {"status": "accepted"}]

    counts = aggregate_counts(_schema(), rows, "status")

    assert [value for value, _ in counts] == ["accepted", "draft", "published"]

import pytest
from parcours.core.dates import (
    parse_partial_date,
    meets_precision_floor,
    same_year,
    ranges_overlap,
    InvalidDateError,
)


def test_parses_year_month_and_day_precision():
    assert parse_partial_date("2024").precision == "year"
    assert parse_partial_date("2024-09").precision == "month"
    assert parse_partial_date("2024-09-30").precision == "day"
    parsed = parse_partial_date("2024-09-30")
    assert (parsed.year, parsed.month, parsed.day) == (2024, 9, 30)


def test_rejects_malformed_dates():
    with pytest.raises(InvalidDateError):
        parse_partial_date("not-a-date")


def test_rejects_calendar_invalid_dates():
    with pytest.raises(InvalidDateError):
        parse_partial_date("2024-13")  # no such month
    with pytest.raises(InvalidDateError):
        parse_partial_date("2024-02-30")  # no such day in February


def test_precision_is_a_floor_not_a_ceiling():
    # A field declared precision:year still accepts a fuller date.
    assert meets_precision_floor("2024-09-30", minimum="year") is True
    assert meets_precision_floor("2024-09", minimum="year") is True
    assert meets_precision_floor("2024", minimum="year") is True
    assert meets_precision_floor("2024", minimum="month") is False
    assert meets_precision_floor("2024-09", minimum="day") is False


def test_same_year():
    assert same_year("2024-09-30", "2024-01") is True
    assert same_year("2024", "2025") is False


def test_ranges_overlap_true_cases():
    assert ranges_overlap("2020-01", "2020-06", "2020-05", "2020-12") is True
    assert ranges_overlap("2020", "2021", "2020-06", "2020-07") is True


def test_ranges_overlap_false_case():
    assert ranges_overlap("2020-01", "2020-02", "2020-06", "2020-07") is False


def test_ranges_overlap_ongoing_end_date():
    # A blank or "present" end means ongoing (open-ended).
    assert ranges_overlap("2020-01", None, "2025-01", "2025-06") is True
    assert ranges_overlap("2020-01", "present", "2099-01", "2099-06") is True

from parcours.core.schema import CategorySchema, DedupRule
from parcours.core.handlers.base import HandlerContext
from parcours.core.handlers.generic import GenericHandler


def _schema(dedup):
    return CategorySchema(name="widgets", handler="generic", dedup=dedup)


def _context(tmp_path):
    return HandlerContext(data_dir=tmp_path)


def test_exact_match_flags_duplicate(tmp_path):
    schema = _schema([DedupRule(conditions=[{"exact": "organization"}], outcome="duplicate")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "organization": "Acme"}
    existing = [{"id": "old", "organization": "Acme"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1
    assert matches[0].existing_row_id == "old"
    assert matches[0].kind == "duplicate"


def test_no_match_when_condition_fails(tmp_path):
    schema = _schema([DedupRule(conditions=[{"exact": "organization"}], outcome="duplicate")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "organization": "Acme"}
    existing = [{"id": "old", "organization": "Widgets Inc"}]

    assert handler.find_matches(entry, existing) == []


def test_never_matches_itself_by_id(tmp_path):
    schema = _schema([DedupRule(conditions=[{"exact": "organization"}], outcome="duplicate")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "same", "organization": "Acme"}
    existing = [{"id": "same", "organization": "Acme"}]

    assert handler.find_matches(entry, existing) == []


def test_fuzzy_and_overlap_combined_condition(tmp_path):
    schema = _schema([DedupRule(
        conditions=[{"fuzzy": "title"}, {"overlap": ["start_date", "end_date"]}],
        outcome="duplicate",
    )])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "title": "Big Grant", "start_date": "2020-01", "end_date": "2020-06"}
    existing = [{"id": "old", "title": "Big Grant", "start_date": "2020-05", "end_date": "2020-12"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1


def test_same_year_matcher(tmp_path):
    schema = _schema([DedupRule(conditions=[{"same_year": "date"}], outcome="duplicate")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "date": "2024-06-01"}
    existing = [{"id": "old", "date": "2024-01-15"}]

    assert len(handler.find_matches(entry, existing)) == 1


def test_related_outcome_is_preserved(tmp_path):
    schema = _schema([DedupRule(conditions=[{"exact": "student_name"}], outcome="related")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "student_name": "Ian Example"}
    existing = [{"id": "old", "student_name": "Ian Example"}]

    matches = handler.find_matches(entry, existing)

    assert matches[0].kind == "related"


def test_generic_handler_validate_returns_no_extra_issues(tmp_path):
    schema = _schema([])
    handler = GenericHandler(schema, _context(tmp_path))
    assert handler.validate({"id": "new"}) == []

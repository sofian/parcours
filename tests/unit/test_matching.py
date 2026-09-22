from parcours.core.matching import fuzzy_match


def test_identical_strings_match():
    assert fuzzy_match("Machine Learning", "Machine Learning") is True


def test_near_duplicate_strings_match():
    assert fuzzy_match("Machine Learning Art", "Machine Learning  Art ") is True


def test_unrelated_strings_do_not_match():
    assert fuzzy_match("Machine Learning", "Completely Different Title") is False


def test_blank_strings_never_match():
    assert fuzzy_match("", "Machine Learning") is False
    assert fuzzy_match("Machine Learning", "") is False

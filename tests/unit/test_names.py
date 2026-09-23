import pytest
from parcours.core.names import InvalidPersonListError, PersonName, parse_person_list


def test_parses_a_single_person():
    people = parse_person_list("Audry, Sofian")
    assert people == [PersonName(last="Audry", first="Sofian")]


def test_parses_multiple_people_separated_by_semicolons():
    people = parse_person_list("Gagné, Rosalie D.; Montenegro, Etienne")
    assert people == [
        PersonName(last="Gagné", first="Rosalie D."),
        PersonName(last="Montenegro", first="Etienne"),
    ]


def test_strips_whitespace_around_names_and_semicolons():
    people = parse_person_list("  Audry ,  Sofian  ;  Gagné , Rosalie D. ")
    assert people == [
        PersonName(last="Audry", first="Sofian"),
        PersonName(last="Gagné", first="Rosalie D."),
    ]


def test_rejects_an_entry_with_no_comma():
    with pytest.raises(InvalidPersonListError):
        parse_person_list("Sofian Audry")


def test_rejects_an_empty_entry_between_semicolons():
    with pytest.raises(InvalidPersonListError):
        parse_person_list("Audry, Sofian; ; Gagné, Rosalie")


def test_rejects_a_blank_last_or_first_name():
    with pytest.raises(InvalidPersonListError):
        parse_person_list(", Sofian")
    with pytest.raises(InvalidPersonListError):
        parse_person_list("Audry, ")

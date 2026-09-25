import xml.etree.ElementTree as ET

import pytest

from parcours.core.ccv_xml import (
    field_bilingual,
    field_date,
    field_lov,
    field_organization,
    field_single_language,
    field_text,
    field_yearmonth,
    find_records,
    parse_ccv_export,
    sub_records,
    try_person_list,
    try_person_list_lenient,
)

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
  <section label="Education">
    <section label="Degrees" recordId="rec-1">
      <field label="Degree Type"><lov id="1">Doctorate</lov></field>
      <field label="Degree Name">
        <value type="Bilingual">Fellowship</value>
        <bilingual><french>Bourse</french><english>Fellowship</english></bilingual>
      </field>
      <field label="Thesis Title"><value type="String">A Thesis</value></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Country" value="Canada" refOrLovId="y"/>
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Other Organization Type"></field>
      <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
      <field label="Degree Received Date"><value type="YearMonth">2022/06</value></field>
      <section label="Supervisors" recordId="rec-1-sup-1">
        <field label="Supervisor Name"><value type="String">Jane Smith</value></field>
        <field label="Start Date"><value type="YearMonth">2018/9</value></field>
        <field label="End Date"><value type="YearMonth">2022/06</value></field>
      </section>
    </section>
  </section>
  <section label="Contributions">
    <section label="Artistic Contributions">
      <section label="Visual Artworks" recordId="rec-2">
        <field label="Artwork Title"><value type="String">Untitled</value></field>
        <field label="Publication Date"><value type="YearMonth">2020/3</value></field>
        <field label="Description / Contribution Value">
          <value type="Bilingual"></value>
          <bilingual><french></french><english></english></bilingual>
        </field>
        <field label="Contribution Role"><value type="String">Author</value></field>
        <field label="Contributors"><value type="String">Smith, Jane; Doe, John</value></field>
      </section>
    </section>
  </section>
</generic-cv:generic-cv>
"""


@pytest.fixture
def root(tmp_path):
    xml_path = tmp_path / "export.xml"
    xml_path.write_text(_SAMPLE, encoding="utf-8")
    root, lang = parse_ccv_export(xml_path)
    assert lang == "en"
    return root


def test_find_records_returns_every_recordid_element_with_its_path(root):
    records = find_records(root)
    paths = [r.path for r in records]
    assert ("Education", "Degrees") in paths
    assert ("Education", "Degrees", "Supervisors") in paths
    assert ("Contributions", "Artistic Contributions", "Visual Artworks") in paths


def test_find_records_defaults_label_to_empty_string_when_missing():
    xml = '<root><section recordId="rec-1"><field label="X"/></section></root>'
    root = ET.fromstring(xml)
    records = find_records(root)
    assert len(records) == 1
    assert records[0].label == ""


def test_field_lov_reads_display_text(root):
    degrees = find_records(root)[0].element
    assert field_lov(degrees, "Degree Type") == "Doctorate"
    assert field_lov(degrees, "Nonexistent Field") == ""


def test_field_text_reads_string_value(root):
    degrees = find_records(root)[0].element
    assert field_text(degrees, "Thesis Title") == "A Thesis"
    assert field_text(degrees, "Other Organization Type") == ""


def test_field_yearmonth_reformats_slash_to_dash_and_zero_pads(root):
    degrees = find_records(root)[0].element
    assert field_yearmonth(degrees, "Degree Start Date") == "2018-09"
    assert field_yearmonth(degrees, "Degree Received Date") == "2022-06"
    assert field_yearmonth(degrees, "Missing Field") == ""


def test_field_yearmonth_returns_empty_on_non_numeric_month():
    xml = '<r label="X" recordId="1"><field label="D"><value type="YearMonth">2020/n.d.</value></field></r>'
    el = ET.fromstring(xml)
    assert field_yearmonth(el, "D") == ""


def test_field_organization_resolves_reftable_linkedwith(root):
    degrees = find_records(root)[0].element
    assert field_organization(degrees) == "Test University"


def test_field_organization_falls_back_to_other_organization(root):
    artwork = find_records(root)[2].element
    # Visual Artworks record has no Organization field at all.
    assert field_organization(artwork) == ""


def test_field_bilingual_prefers_split_form(root):
    degrees = find_records(root)[0].element
    fr, en = field_bilingual(degrees, "Degree Name", default_lang="en")
    assert fr == "Bourse"
    assert en == "Fellowship"


def test_field_bilingual_returns_blank_when_both_blank(root):
    artwork = find_records(root)[2].element
    fr, en = field_bilingual(artwork, "Description / Contribution Value", default_lang="en")
    assert fr == ""
    assert en == ""


def test_field_single_language_routes_by_default_lang(root):
    artwork = find_records(root)[2].element
    fr, en = field_single_language(artwork, "Artwork Title", default_lang="en")
    assert fr == ""
    assert en == "Untitled"


def test_sub_records_finds_direct_children_only(root):
    degrees = find_records(root)[0].element
    supervisors = sub_records(degrees, "Supervisors")
    assert len(supervisors) == 1
    assert field_text(supervisors[0], "Supervisor Name") == "Jane Smith"


def test_try_person_list_returns_raw_on_valid_format():
    assert try_person_list("Smith, Jane; Doe, John") == "Smith, Jane; Doe, John"


def test_try_person_list_returns_none_on_invalid_format():
    assert try_person_list("Jane Smith") is None


def test_try_person_list_returns_none_on_blank():
    assert try_person_list("") is None
    assert try_person_list("   ") is None


def test_try_person_list_lenient_returns_none_on_blank():
    assert try_person_list_lenient("") is None
    assert try_person_list_lenient("   ") is None


def test_try_person_list_lenient_inverts_a_single_natural_order_name():
    assert try_person_list_lenient("Chris Salter") == "Salter, Chris"


def test_try_person_list_lenient_inverts_a_middle_name_into_the_first_name_part():
    assert try_person_list_lenient("Erin Marie Gee") == "Gee, Erin Marie"


def test_try_person_list_lenient_returns_none_for_a_single_token_name():
    assert try_person_list_lenient("Prince") is None


def test_try_person_list_lenient_splits_a_semicolon_separated_natural_order_list():
    assert (
        try_person_list_lenient("Edwige Armand; Camille Prunet; Nicolas Reeves")
        == "Armand, Edwige; Prunet, Camille; Reeves, Nicolas"
    )


def test_try_person_list_lenient_splits_a_comma_separated_natural_order_list():
    assert (
        try_person_list_lenient("Manuelle Freire, Sylvain Martet, Victor Drouin-Trempe")
        == "Freire, Manuelle; Martet, Sylvain; Drouin-Trempe, Victor"
    )


def test_try_person_list_lenient_handles_a_trailing_and_before_the_last_name():
    assert (
        try_person_list_lenient("Ben Bogart, Stephanie Dinkins, Suzanne Kite et Stephen Kelly")
        == "Bogart, Ben; Dinkins, Stephanie; Kite, Suzanne; Kelly, Stephen"
    )
    assert try_person_list_lenient("Alastair Summerlee and Matthew Kean") == "Summerlee, Alastair; Kean, Matthew"


def test_try_person_list_lenient_strips_a_trailing_period():
    assert try_person_list_lenient("Ben Bogart et Allison Parrish.") == "Bogart, Ben; Parrish, Allison"


def test_try_person_list_lenient_preserves_a_hyphenated_surname_as_one_token():
    assert try_person_list_lenient("Rosalie Dumont-Gagné") == "Dumont-Gagné, Rosalie"


def test_try_person_list_lenient_returns_none_if_any_single_name_is_ambiguous():
    # "Prince" has no given name to separate out, so the whole list is
    # rejected rather than guessing — same "never guess" rule as everywhere
    # else in this codebase.
    assert try_person_list_lenient("Chris Salter; Prince") is None


def test_field_date_passes_through_iso_date():
    xml = '<r label="X" recordId="1"><field label="D"><value type="Date">2024-05-17</value></field></r>'
    el = ET.fromstring(xml)
    assert field_date(el, "D") == "2024-05-17"
    assert field_date(el, "Missing") == ""

import xml.etree.ElementTree as ET

from parcours.core.import_ccv import ImportContext, MappedRow, map_record


def _record(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def _ctx():
    return ImportContext(default_currency="CAD", own_name=("Doe", "Jane"))


def test_map_education_degree():
    el = _record("""
    <section label="Degrees" recordId="r1">
      <field label="Degree Type"><lov id="1">Doctorate</lov></field>
      <field label="Degree Name">
        <value type="Bilingual">Ph.D.</value>
        <bilingual><french>Ph. D.</french><english>Ph.D.</english></bilingual>
      </field>
      <field label="Specialization">
        <value type="Bilingual"></value>
        <bilingual><french></french><english></english></bilingual>
      </field>
      <field label="Thesis Title"><value type="String">A Study</value></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Degree Status"><lov id="2">Completed</lov></field>
      <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
      <field label="Degree Received Date"><value type="YearMonth">2022/6</value></field>
      <section label="Supervisors" recordId="r1s1">
        <field label="Supervisor Name"><value type="String">Jane Smith</value></field>
      </section>
      <section label="Supervisors" recordId="r1s2">
        <field label="Supervisor Name"><value type="String">John Doe</value></field>
      </section>
    </section>
    """)
    row = map_record(el, "Degrees", "en", _ctx())
    assert isinstance(row, MappedRow)
    assert row.category == "education"
    assert row.fields["degree_type"] == "doctorate"
    assert row.fields["degree_name_fr"] == "Ph. D."
    assert row.fields["degree_name_en"] == "Ph.D."
    assert row.fields["organization"] == "Test University"
    assert row.fields["degree_status"] == "completed"
    assert row.fields["start_date"] == "2018-09"
    assert row.fields["end_date"] == "2022-06"
    assert row.fields["advisor"] == "Jane Smith; John Doe"
    assert row.fields["thesis_title"] == "A Study"


def test_map_presentation_with_valid_co_presenters():
    el = _record("""
    <section label="Presentations" recordId="r2">
      <field label="Presentation Title"><value type="String">My Talk</value></field>
      <field label="Conference / Event Name"><value type="String">Some Conference</value></field>
      <field label="Invited?"><lov id="1">Yes</lov></field>
      <field label="Keynote?"><lov id="2">No</lov></field>
      <field label="Presentation Year"><value type="Year">2023</value></field>
      <field label="URL"><value type="String">http://example.com</value></field>
      <field label="Co-Presenters"><value type="String">Smith, Jane; Doe, John</value></field>
    </section>
    """)
    row = map_record(el, "Presentations", "en", _ctx())
    assert row.fields["title_en"] == "My Talk"
    assert row.fields["title_fr"] == ""
    assert row.fields["event_en"] == "Some Conference"
    assert row.fields["invited"] == "true"
    assert row.fields["keynote"] == "false"
    assert row.fields["date"] == "2023"
    assert row.fields["co_presenters"] == "Smith, Jane; Doe, John"
    assert row.flag is None


def test_map_presentation_flags_unparseable_co_presenters():
    el = _record("""
    <section label="Presentations" recordId="r3">
      <field label="Presentation Title"><value type="String">Another Talk</value></field>
      <field label="Presentation Year"><value type="Year">2022</value></field>
      <field label="Co-Presenters"><value type="String">Jane Smith and John Doe</value></field>
    </section>
    """)
    row = map_record(el, "Presentations", "en", _ctx())
    assert row.fields["co_presenters"] == ""
    assert row.flag is not None
    assert "co_presenters" in row.flag


def test_map_recognitions():
    el = _record("""
    <section label="Recognitions" recordId="r4">
      <field label="Recognition Type"><lov id="1">Prize / Award</lov></field>
      <field label="Recognition Name"><value type="String">Best Paper</value></field>
      <field label="Other Organization"><value type="String">Some Society</value></field>
      <field label="Effective Date"><value type="YearMonth">2021/5</value></field>
      <field label="Amount"><value type="Number">1000</value></field>
      <field label="Currency"><lov id="2">CAD</lov></field>
      <field label="Description">
        <value type="Bilingual"></value>
        <bilingual><french>Une description</french><english>A description</english></bilingual>
      </field>
    </section>
    """)
    row = map_record(el, "Recognitions", "en", _ctx())
    assert row.fields["recognition_type"] == "prize"
    assert row.fields["name"] == "Best Paper"
    assert row.fields["organization"] == "Some Society"
    assert row.fields["role"] == "recipient"
    assert row.fields["date"] == "2021-05"
    assert row.fields["amount"] == "1000"
    assert row.fields["currency"] == "CAD"
    assert row.fields["description_en"] == "A description"
    assert row.fields["description_fr"] == "Une description"


def test_map_recognitions_defaults_currency_when_ccv_gives_none():
    el = _record("""
    <section label="Recognitions" recordId="r5">
      <field label="Recognition Type"><lov id="1">Citation</lov></field>
      <field label="Recognition Name"><value type="String">Mention</value></field>
      <field label="Effective Date"><value type="YearMonth">2020/1</value></field>
    </section>
    """)
    row = map_record(el, "Recognitions", "en", _ctx())
    assert row.fields["amount"] == ""
    assert row.fields["currency"] == ""


def test_map_teaching_course_development():
    el = _record("""
    <section label="Course Development" recordId="r6">
      <field label="Role"><value type="String">Professor</value></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Department"><value type="String">Media Studies</value></field>
      <field label="Course Title"><value type="String">Intro to Media</value></field>
      <field label="Date First Taught"><value type="YearMonth">2019/9</value></field>
    </section>
    """)
    row = map_record(el, "Course Development", "en", _ctx())
    assert row.category == "teaching"
    assert row.fields["course_label"] == ""
    assert row.fields["title_en"] == "Intro to Media"
    assert row.fields["role"] == "Professor"
    assert row.fields["organization"] == "Test University"
    assert row.fields["department"] == "Media Studies"
    assert row.fields["date"] == "2019-09"


def test_map_press_broadcast_interview():
    el = _record("""
    <section label="Broadcast Interviews" recordId="r7">
      <field label="Interviewer"><value type="String">A Journalist</value></field>
      <field label="Program"><value type="String">Morning Show</value></field>
      <field label="Network"><value type="String">Test Radio</value></field>
      <field label="First Broadcast Date"><value type="Date">2021-03-14</value></field>
      <field label="Description / Contribution Value">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>A discussion</english></bilingual>
      </field>
      <field label="URL"><value type="String">http://example.com/clip</value></field>
    </section>
    """)
    row = map_record(el, "Broadcast Interviews", "en", _ctx())
    assert row.category == "press"
    assert row.fields["author"] == "A Journalist"
    assert row.fields["outlet"] == "Test Radio"
    assert row.fields["program"] == "Morning Show"
    assert row.fields["date"] == "2021-03-14"
    assert row.fields["description_en"] == "A discussion"


def test_map_press_text_interview_has_no_program():
    el = _record("""
    <section label="Text Interviews" recordId="r8">
      <field label="Interviewer"><value type="String">A Journalist</value></field>
      <field label="Forum"><value type="String">Test Magazine</value></field>
      <field label="Publication Date"><value type="Date">2020-11-02</value></field>
    </section>
    """)
    row = map_record(el, "Text Interviews", "en", _ctx())
    assert row.fields["outlet"] == "Test Magazine"
    assert row.fields["program"] == ""
    assert row.fields["date"] == "2020-11-02"


def test_map_positions_academic():
    el = _record("""
    <section label="Academic Work Experience" recordId="r9">
      <field label="Position Title"><value type="String">Professor</value></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Faculty / School / Campus"><value type="String">Media</value></field>
      <field label="Department"><value type="String">Studies</value></field>
      <field label="Position Status"><lov id="1">Full-time</lov></field>
      <field label="Start Date"><value type="YearMonth">2015/8</value></field>
    </section>
    """)
    row = map_record(el, "Academic Work Experience", "en", _ctx())
    assert row.category == "positions"
    assert row.fields["type"] == "academic"
    assert row.fields["title_en"] == "Professor"
    assert row.fields["organization"] == "Test University"
    assert row.fields["faculty"] == "Media"
    assert row.fields["department"] == "Studies"
    assert row.fields["position_status"] == "full-time"
    assert row.fields["start_date"] == "2015-08"


def test_map_positions_affiliation_title_is_truly_bilingual():
    el = _record("""
    <section label="Affiliations" recordId="r10">
      <field label="Position Title">
        <value type="Bilingual">Member</value>
        <bilingual><french>Membre</french><english>Member</english></bilingual>
      </field>
      <field label="Other Organization"><value type="String">Some Institute</value></field>
      <field label="Department"><value type="String">N/A</value></field>
      <field label="Start Date"><value type="YearMonth">2017/1</value></field>
    </section>
    """)
    row = map_record(el, "Affiliations", "en", _ctx())
    assert row.fields["type"] == "affiliation"
    assert row.fields["title_en"] == "Member"
    assert row.fields["title_fr"] == "Membre"
    assert row.fields["organization"] == "Some Institute"


def test_map_positions_non_academic_uses_unit_division_as_department():
    el = _record("""
    <section label="Non-academic Work Experience" recordId="r11">
      <field label="Position Title"><value type="String">Consultant</value></field>
      <field label="Other Organization"><value type="String">Some Company</value></field>
      <field label="Unit / Division"><value type="String">R&amp;D</value></field>
      <field label="Start Date"><value type="YearMonth">2014/1</value></field>
      <field label="End Date"><value type="YearMonth">2015/1</value></field>
    </section>
    """)
    row = map_record(el, "Non-academic Work Experience", "en", _ctx())
    assert row.fields["type"] == "non-academic"
    assert row.fields["organization"] == "Some Company"
    assert row.fields["department"] == "R&D"
    assert row.fields["faculty"] == ""

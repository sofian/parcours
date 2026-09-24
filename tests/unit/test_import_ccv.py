import json
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


def test_map_service_graduate_examination():
    el = _record("""
    <section label="Graduate Examination Activities" recordId="s1">
      <field label="Graduate Examination Activity Role"><lov id="1">Thesis Defense Examiner</lov></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Start Date"><value type="YearMonth">2020/1</value></field>
      <field label="End Date"><value type="YearMonth">2020/1</value></field>
      <field label="Student Name"><value type="String">A Student</value></field>
    </section>
    """)
    row = map_record(el, "Graduate Examination Activities", "en", _ctx())
    assert row.category == "service"
    assert row.fields["type"] == "graduate-examination"
    assert row.fields["role"] == "Thesis Defense Examiner"
    assert row.fields["organization"] == "Test University"
    assert row.fields["detail"] == "A Student"
    assert row.fields["start_date"] == "2020-01"


def test_map_service_funding_review():
    el = _record("""
    <section label="Research Funding Application Assessment Activities" recordId="s2">
      <field label="Funding Reviewer Role"><lov id="1">External Reviewer</lov></field>
      <field label="Other Organization"><value type="String">Some Agency</value></field>
      <field label="Committee Name"><value type="String">Panel A</value></field>
      <field label="Start Date"><value type="YearMonth">2019/1</value></field>
    </section>
    """)
    row = map_record(el, "Research Funding Application Assessment Activities", "en", _ctx())
    assert row.fields["type"] == "funding-review"
    assert row.fields["role"] == "External Reviewer"
    assert row.fields["organization"] == "Some Agency"
    assert row.fields["detail"] == "Panel A"


def test_map_service_volunteer():
    el = _record("""
    <section label="Community and Volunteer Activities" recordId="s3">
      <field label="Role"><value type="String">Board Member</value></field>
      <field label="Other Organization"><value type="String">Local Charity</value></field>
      <field label="Start Date"><value type="YearMonth">2018/1</value></field>
      <field label="Activity Description">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>Helped organize events</english></bilingual>
      </field>
    </section>
    """)
    row = map_record(el, "Community and Volunteer Activities", "en", _ctx())
    assert row.fields["type"] == "volunteer"
    assert row.fields["role"] == "Board Member"
    assert row.fields["detail"] == "Helped organize events"


def test_map_service_committee_membership():
    el = _record("""
    <section label="Committee Memberships" recordId="s4">
      <field label="Role"><lov id="1">Committee Member</lov></field>
      <field label="Committee Name"><value type="String">Hiring Committee</value></field>
      <field label="Other Organization"><value type="String">Test University</value></field>
      <field label="Membership Start Date"><value type="YearMonth">2021/1</value></field>
      <field label="Membership End Date"><value type="YearMonth">2022/1</value></field>
    </section>
    """)
    row = map_record(el, "Committee Memberships", "en", _ctx())
    assert row.fields["type"] == "committee"
    assert row.fields["role"] == "Committee Member"
    assert row.fields["detail"] == "Hiring Committee"
    assert row.fields["start_date"] == "2021-01"
    assert row.fields["end_date"] == "2022-01"


def test_map_service_program_development():
    el = _record("""
    <section label="Program Development" recordId="s5">
      <field label="Role"><value type="String">Chair</value></field>
      <field label="Other Organization"><value type="String">Test University</value></field>
      <field label="Program Title"><value type="String">New MFA Program</value></field>
      <field label="Program Description">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>A revised curriculum</english></bilingual>
      </field>
      <field label="Date First Taught"><value type="YearMonth">2020/9</value></field>
    </section>
    """)
    row = map_record(el, "Program Development", "en", _ctx())
    assert row.category == "service"
    assert row.fields["type"] == "program-development"
    assert row.fields["start_date"] == "2020-09"
    assert row.fields["end_date"] == ""
    assert "New MFA Program" in row.fields["detail"]
    assert "A revised curriculum" in row.fields["detail"]


def test_map_outreach():
    el = _record("""
    <section label="Knowledge and Technology Translation" recordId="o1">
      <field label="Role"><value type="String">Consultant</value></field>
      <field label="Knowledge and Technology Translation Activity Type"><lov id="1">Consulting for Industry</lov></field>
      <field label="Group/Organization/Business Serviced"><value type="String">A Company</value></field>
      <field label="Target Stakeholder"><lov id="2">Industrial Association/Producer Group</lov></field>
      <field label="References / Citations / Web Sites"><value type="String">http://example.com</value></field>
      <field label="Start Date"><value type="YearMonth">2017/1</value></field>
      <field label="Activity Description">
        <value type="Bilingual"></value>
        <bilingual><french>Une activite</french><english>An activity</english></bilingual>
      </field>
    </section>
    """)
    row = map_record(el, "Knowledge and Technology Translation", "en", _ctx())
    assert row.category == "outreach"
    assert row.fields["activity_type"] == "industry-consulting"
    assert row.fields["target_stakeholder"] == "industry-association"
    assert row.fields["organization"] == "A Company"
    assert row.fields["role"] == "Consultant"
    assert row.fields["url"] == "http://example.com"
    assert row.fields["description_en"] == "An activity"
    assert row.fields["description_fr"] == "Une activite"


def test_map_students():
    el = _record("""
    <section label="Student/Postdoctoral Supervision" recordId="st1">
      <field label="Supervision Role"><lov id="1">Principal Supervisor</lov></field>
      <field label="Supervision Start Date"><value type="YearMonth">2019/9</value></field>
      <field label="Supervision End Date"><value type="YearMonth">2023/6</value></field>
      <field label="Student Name"><value type="String">A Student</value></field>
      <field label="Student Institution"><value type="String">Test University</value></field>
      <field label="Degree Type or Postdoctoral Status"><lov id="2">Doctorate</lov></field>
      <field label="Student Degree Status"><lov id="3">Completed</lov></field>
      <field label="Student Degree Start Date"><value type="YearMonth">2019/9</value></field>
      <field label="Student Degree Received Date"><value type="YearMonth">2023/6</value></field>
      <field label="Thesis/Project Title"><value type="String">A Dissertation</value></field>
      <field label="Present Position"><value type="String">Postdoc</value></field>
      <field label="Present Organization"><value type="String">Another University</value></field>
    </section>
    """)
    row = map_record(el, "Student/Postdoctoral Supervision", "en", _ctx())
    assert row.category == "students"
    assert row.fields["student_name"] == "A Student"
    assert row.fields["role"] == "principal-supervisor"
    assert row.fields["degree_type"] == "doctorate"
    assert row.fields["degree_status"] == "completed"
    assert row.fields["supervision_start_date"] == "2019-09"
    assert row.fields["supervision_end_date"] == "2023-06"
    assert row.fields["degree_start_date"] == "2019-09"
    assert row.fields["degree_end_date"] == "2023-06"
    assert row.fields["thesis_title"] == "A Dissertation"
    assert row.fields["present_position"] == "Postdoc"
    assert row.fields["present_organization"] == "Another University"


def test_map_visual_artwork_contributors_parses_and_filters_self():
    el = _record("""
    <section label="Visual Artworks" recordId="a1">
      <field label="Artwork Title"><value type="String">Untitled</value></field>
      <field label="Publication Date"><value type="YearMonth">2020/3</value></field>
      <field label="Description / Contribution Value">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>A description</english></bilingual>
      </field>
      <field label="URL"><value type="String">http://example.com</value></field>
      <field label="Contribution Role"><value type="String">Artist</value></field>
      <field label="Contributors"><value type="String">Doe, Jane; Smith, John</value></field>
    </section>
    """)
    row = map_record(el, "Visual Artworks", "en", _ctx())
    assert row.category == "artworks"
    assert row.fields["title_en"] == "Untitled"
    assert row.fields["date"] == "2020"
    assert row.fields["role"] == "author"
    assert row.fields["co_authors"] == "Smith, John"
    assert row.fields["collaborators"] == ""
    assert row.flag is None


def test_map_visual_artwork_flags_unparseable_contributors():
    el = _record("""
    <section label="Visual Artworks" recordId="a2">
      <field label="Artwork Title"><value type="String">Another Piece</value></field>
      <field label="Publication Date"><value type="YearMonth">2019/1</value></field>
      <field label="Contribution Role"><value type="String">Collaborator</value></field>
      <field label="Contributors"><value type="String">John Smith and Jane Doe</value></field>
    </section>
    """)
    row = map_record(el, "Visual Artworks", "en", _ctx())
    assert row.fields["role"] == "collaborator"
    assert row.fields["co_authors"] == ""
    assert row.flag is not None


def test_map_visual_artwork_unrecognized_role_defaults_to_author():
    el = _record("""
    <section label="Visual Artworks" recordId="a3">
      <field label="Artwork Title"><value type="String">A Piece</value></field>
      <field label="Publication Date"><value type="YearMonth">2018/1</value></field>
    </section>
    """)
    row = map_record(el, "Visual Artworks", "en", _ctx())
    assert row.fields["role"] == "author"


def test_map_visual_artwork_contributors_all_self_leaves_co_authors_blank_no_flag():
    el = _record("""
    <section label="Visual Artworks" recordId="a5">
      <field label="Artwork Title"><value type="String">Solo Piece</value></field>
      <field label="Publication Date"><value type="YearMonth">2021/1</value></field>
      <field label="Contribution Role"><value type="String">Author</value></field>
      <field label="Contributors"><value type="String">Doe, Jane</value></field>
    </section>
    """)
    row = map_record(el, "Visual Artworks", "en", _ctx())
    assert row.fields["co_authors"] == ""
    assert row.flag is None


def test_map_audio_recording_uses_piece_title_and_release_date_year():
    el = _record("""
    <section label="Audio Recordings" recordId="a4">
      <field label="Piece Title"><value type="String">A Track</value></field>
      <field label="Release Date"><value type="Date">2017-06-01</value></field>
    </section>
    """)
    row = map_record(el, "Audio Recordings", "en", _ctx())
    assert row.category == "artworks"
    assert row.fields["title_en"] == "A Track"
    assert row.fields["date"] == "2017"


def test_map_artistic_exhibition():
    el = _record("""
    <section label="Artistic Exhibitions" recordId="e1">
      <field label="Title of Work"><value type="String">A Show</value></field>
      <field label="Venue"><value type="String">A Gallery</value></field>
      <field label="Date of First Performance"><value type="Date">2021-04-10</value></field>
    </section>
    """)
    row = map_record(el, "Artistic Exhibitions", "en", _ctx())
    assert row.category == "exhibitions"
    assert row.fields["title_en"] == "A Show"
    assert row.fields["venue"] == "A Gallery"
    assert row.fields["start_date"] == "2021-04-10"
    assert row.fields["event"] == ""
    assert row.fields["location"] == ""
    assert row.fields["curator"] == ""


def test_map_grant_single_funding_source():
    el = _record("""
    <section label="Research Funding History" recordId="g1">
      <field label="Funding Title"><value type="String">A Grant</value></field>
      <field label="Funding Role"><lov id="1">Principal Investigator</lov></field>
      <field label="Funding Status"><lov id="2">Awarded</lov></field>
      <field label="Funding Start Date"><value type="YearMonth">2021/4</value></field>
      <field label="Funding End Date"><value type="YearMonth">2024/3</value></field>
      <field label="Project Description">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>A project</english></bilingual>
      </field>
      <field label="Research Uptake">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>Some uptake</english></bilingual>
      </field>
      <section label="Funding Sources" recordId="g1f1">
        <field label="Funding Organization"><lov id="3">Test Funder</lov></field>
        <field label="Program Name"><value type="String">Test Program</value></field>
        <field label="Total Funding"><value type="Number">50000</value></field>
        <field label="Currency of Total Funding"><lov id="4">CAD</lov></field>
      </section>
    </section>
    """)
    row = map_record(el, "Research Funding History", "en", _ctx())
    assert row.category == "grants"
    assert row.fields["title_en"] == "A Grant"
    assert row.fields["funder"] == "Test Funder"
    assert row.fields["program"] == "Test Program"
    assert row.fields["role"] == "pi"
    assert row.fields["status"] == "awarded"
    assert row.fields["start_date"] == "2021-04"
    assert row.fields["end_date"] == "2024-03"
    assert row.fields["amount"] == "50000"
    assert row.fields["currency"] == "CAD"
    assert "A project" in row.fields["note_en"]
    assert "Some uptake" in row.fields["note_en"]
    assert row.fields["co_investigators"] == ""
    assert row.flag is None


def test_map_grant_completed_status_collapses_to_awarded():
    el = _record("""
    <section label="Research Funding History" recordId="g2">
      <field label="Funding Title"><value type="String">Another Grant</value></field>
      <field label="Funding Role"><lov id="1">Co-investigator</lov></field>
      <field label="Funding Status"><lov id="2">Completed</lov></field>
      <field label="Funding Start Date"><value type="YearMonth">2015/1</value></field>
    </section>
    """)
    row = map_record(el, "Research Funding History", "en", _ctx())
    assert row.fields["role"] == "co-pi"
    assert row.fields["status"] == "awarded"


def test_map_grant_flags_multiple_funding_sources():
    el = _record("""
    <section label="Research Funding History" recordId="g3">
      <field label="Funding Title"><value type="String">Multi-source Grant</value></field>
      <field label="Funding Start Date"><value type="YearMonth">2016/1</value></field>
      <section label="Funding Sources" recordId="g3f1">
        <field label="Funding Organization"><lov id="1">Funder A</lov></field>
        <field label="Total Funding"><value type="Number">10000</value></field>
      </section>
      <section label="Funding Sources" recordId="g3f2">
        <field label="Funding Organization"><lov id="2">Funder B</lov></field>
        <field label="Total Funding"><value type="Number">5000</value></field>
      </section>
    </section>
    """)
    row = map_record(el, "Research Funding History", "en", _ctx())
    assert row.fields["funder"] == "Funder A"
    assert row.fields["amount"] == "10000"
    assert row.flag is not None
    assert "Funding Sources" in row.flag
    assert "Funder B" in row.flag


def test_map_grant_flags_other_investigators_unparseable():
    el = _record("""
    <section label="Research Funding History" recordId="g4">
      <field label="Funding Title"><value type="String">Team Grant</value></field>
      <field label="Funding Start Date"><value type="YearMonth">2017/1</value></field>
      <section label="Other Investigators" recordId="g4i1">
        <field label="Investigator Name"><value type="String">Jane Smith</value></field>
      </section>
      <section label="Other Investigators" recordId="g4i2">
        <field label="Investigator Name"><value type="String">John Doe</value></field>
      </section>
    </section>
    """)
    row = map_record(el, "Research Funding History", "en", _ctx())
    assert row.fields["co_investigators"] == ""
    assert row.flag is not None
    assert "co_investigators" in row.flag
    assert "Jane Smith" in row.flag
    assert "John Doe" in row.flag


from parcours.core.import_ccv import extract_zotero_candidate


def test_extract_zotero_candidate_journal_article():
    el = _record("""
    <section label="Journal Articles" recordId="p1">
      <field label="Article Title"><value type="String">A Widget Study</value></field>
      <field label="Year"><value type="Year">2020</value></field>
    </section>
    """)
    candidate = extract_zotero_candidate(el, "Journal Articles", "en")
    assert candidate.title == "A Widget Study"
    assert candidate.year == 2020
    assert candidate.ccv_label == "Journal Articles"


def test_extract_zotero_candidate_book():
    el = _record('<section label="Books" recordId="p2">'
                 '<field label="Book Title"><value type="String">A Book</value></field>'
                 '<field label="Year"><value type="Year">2018</value></field>'
                 '</section>')
    candidate = extract_zotero_candidate(el, "Books", "en")
    assert candidate.title == "A Book"
    assert candidate.year == 2018


def test_extract_zotero_candidate_thesis_uses_completion_year():
    el = _record('<section label="Thesis/Dissertation" recordId="p3">'
                 '<field label="Dissertation Title"><value type="String">A Thesis</value></field>'
                 '<field label="Completion Year"><value type="Year">2015</value></field>'
                 '</section>')
    candidate = extract_zotero_candidate(el, "Thesis/Dissertation", "en")
    assert candidate.title == "A Thesis"
    assert candidate.year == 2015


def test_extract_zotero_candidate_exhibition_catalogue_uses_yearmonth():
    el = _record('<section label="Exhibition Catalogues" recordId="p4">'
                 '<field label="Catalogue Title"><value type="String">A Catalogue</value></field>'
                 '<field label="Publication Date"><value type="YearMonth">2019/6</value></field>'
                 '</section>')
    candidate = extract_zotero_candidate(el, "Exhibition Catalogues", "en")
    assert candidate.title == "A Catalogue"
    assert candidate.year == 2019


def test_extract_zotero_candidate_blank_year_is_none():
    el = _record('<section label="Online Resources" recordId="p5">'
                 '<field label="Title"><value type="String">A Resource</value></field>'
                 '</section>')
    candidate = extract_zotero_candidate(el, "Online Resources", "en")
    assert candidate.year is None


def test_extract_zotero_candidate_non_numeric_year_is_none():
    el = _record('<section label="Journal Articles" recordId="p6">'
                 '<field label="Article Title"><value type="String">A Widget Study</value></field>'
                 '<field label="Year"><value type="Year">n.d.</value></field>'
                 '</section>')
    candidate = extract_zotero_candidate(el, "Journal Articles", "en")
    assert candidate.year is None


import textwrap

from parcours.core.import_ccv import ImportReport, plan_import, write_import


def _minimal_data_dir(tmp_path):
    (tmp_path / "categories").mkdir()
    education_schema = tmp_path / "categories" / "education.yaml"
    education_schema.write_text(textwrap.dedent("""
        name: education
        handler: generic
        fields:
          - {name: id, generated: true}
          - {name: degree_type, required: true}
          - {name: degree_name_en}
          - {name: degree_name_fr}
          - {name: specialization_en}
          - {name: specialization_fr}
          - {name: organization, required: true}
          - {name: degree_status, required: true}
          - {name: start_date, type: date, precision: month, required: true}
          - {name: end_date, type: date, precision: month}
          - {name: thesis_title}
          - {name: advisor}
          - {name: note_en}
          - {name: note_fr}
        dedup:
          - when: [{exact: organization}, {exact: degree_type}, {same_year: start_date}]
            as: duplicate
    """), encoding="utf-8")
    (tmp_path / "education.csv").write_text(
        "id,degree_type,degree_name_en,degree_name_fr,specialization_en,specialization_fr,"
        "organization,degree_status,start_date,end_date,thesis_title,advisor,note_en,note_fr\n",
        encoding="utf-8",
    )
    identity = tmp_path / "identity.yaml"
    identity.write_text("name:\n  first: Jane\n  last: Doe\n", encoding="utf-8")
    parco_yaml = tmp_path / "parco.yaml"
    parco_yaml.write_text("currency:\n  default: CAD\n  report: CAD\n", encoding="utf-8")
    return tmp_path


def _write_xml(tmp_path, xml: str):
    path = tmp_path / "export.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def test_plan_import_maps_a_known_record():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        data_dir = _minimal_data_dir(Path(d))
        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Education">
            <section label="Degrees" recordId="r1">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Organization">
                <refTable refValueId="x" label="Organization">
                  <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
                </refTable>
              </field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert isinstance(report, ImportReport)
        assert len(report.to_write) == 1
        assert report.to_write[0].category == "education"
        assert report.to_write[0].fields["organization"] == "Test University"


def test_plan_import_ignores_known_sub_records_without_reporting_them_skipped():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        data_dir = _minimal_data_dir(Path(d))
        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Education">
            <section label="Degrees" recordId="r1">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
              <section label="Supervisors" recordId="r1s1">
                <field label="Supervisor Name"><value type="String">Jane Smith</value></field>
              </section>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert "Supervisors" not in report.skipped_labels


def test_plan_import_reports_genuinely_unmapped_records_as_skipped():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        data_dir = _minimal_data_dir(Path(d))
        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Personal Information">
            <section label="Address" recordId="addr1">
              <field label="City"><value type="String">Somewhere</value></field>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert report.skipped_labels.get("Address") == 1


def test_plan_import_flags_dedup_duplicate_but_still_writes_it():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        data_dir = _minimal_data_dir(Path(d))
        # Seed an existing row that will collide via the dedup rule
        # (exact organization, exact degree_type, same_year start_date).
        (data_dir / "education.csv").write_text(
            "id,degree_type,degree_name_en,degree_name_fr,specialization_en,specialization_fr,"
            "organization,degree_status,start_date,end_date,thesis_title,advisor,note_en,note_fr\n"
            "exist1,doctorate,,,,,Test University,completed,2018-09,,,,,\n",
            encoding="utf-8",
        )
        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Education">
            <section label="Degrees" recordId="r1">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Organization">
                <refTable refValueId="x" label="Organization">
                  <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
                </refTable>
              </field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert len(report.to_write) == 1
        assert 0 in report.dedup_matches
        assert report.dedup_matches[0][0].kind == "duplicate"


def test_write_import_writes_rows_and_never_commits():
    import subprocess
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        data_dir = _minimal_data_dir(Path(d))
        subprocess.run(["git", "init"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=data_dir, check=True, capture_output=True)

        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Education">
            <section label="Degrees" recordId="r1">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        touched = write_import(data_dir, report)

        assert touched == ["education.csv"]
        content = (data_dir / "education.csv").read_text(encoding="utf-8")
        assert "doctorate" in content

        status = subprocess.run(["git", "status", "--porcelain"], cwd=data_dir, check=True, capture_output=True, text=True)
        assert "education.csv" in status.stdout  # uncommitted


def _add_publications_category(data_dir):
    (data_dir / "categories" / "publications.yaml").write_text(textwrap.dedent("""
        name: publications
        handler: publications
        options:
          json: reference/library.json
        fields:
          - {name: id, generated: true}
          - {name: weight, type: int}
          - {name: citekey, required: true}
          - {name: status, required: true}
          - {name: refereed, type: bool}
          - {name: invited, type: bool}
          - {name: featured, type: bool}
          - {name: note_en}
          - {name: note_fr}
    """), encoding="utf-8")
    (data_dir / "publications.csv").write_text(
        "id,weight,citekey,status,refereed,invited,featured,note_en,note_fr\n",
        encoding="utf-8",
    )
    reference_dir = data_dir / "reference"
    reference_dir.mkdir()
    (reference_dir / "library.json").write_text(json.dumps([
        {"id": "smith2020article", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
    ]), encoding="utf-8")
    return data_dir


def test_plan_import_dispatches_zotero_matched_records():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        data_dir = _minimal_data_dir(Path(d))
        _add_publications_category(data_dir)
        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Contributions">
            <section label="Publications">
              <section label="Journal Articles" recordId="p1">
                <field label="Article Title"><value type="String">A Widget Study</value></field>
                <field label="Year"><value type="Year">2020</value></field>
              </section>
              <section label="Journal Articles" recordId="p2">
                <field label="Article Title"><value type="String">Totally Unrelated Nonexistent Title</value></field>
                <field label="Year"><value type="Year">1999</value></field>
              </section>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert len(report.to_write) == 1
        assert report.to_write[0].category == "publications"
        assert report.to_write[0].fields["citekey"] == "smith2020article"
        assert len(report.flagged) == 1
        assert report.flagged[0].ccv_label == "Journal Articles"
        assert "No confident match in your citation export" in report.flagged[0].reason


def test_write_import_generates_distinct_ids_for_multiple_new_rows_same_category():
    import subprocess
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        data_dir = _minimal_data_dir(Path(d))
        subprocess.run(["git", "init"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=data_dir, check=True, capture_output=True)

        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Education">
            <section label="Degrees" recordId="r1">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
            </section>
            <section label="Degrees" recordId="r2">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2019/9</value></field>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert len(report.to_write) == 2

        write_import(data_dir, report)

        rows = (data_dir / "education.csv").read_text(encoding="utf-8").splitlines()[1:]
        ids = [row.split(",")[0] for row in rows]
        assert len(ids) == 2
        assert len(set(ids)) == 2  # distinct, no collision

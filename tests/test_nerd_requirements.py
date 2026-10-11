"""NERD user-supplied requirements: complete list and private, read-only UI."""
from app.services.nerd_requirements import (
    NERD_REQUIREMENT_SECTIONS,
    REQUIREMENT_TOTAL,
)


def test_seven_groups_and_thirty_eight_distinct_items():
    assert [section["title"] for section in NERD_REQUIREMENT_SECTIONS] == [
        "Personal Information",
        "Contact Information",
        "Next of Kin",
        "Academic Data",
        "Supervisor Details",
        "HOD Details",
        "Documents to Prepare",
    ]
    assert [len(section["items"]) for section in NERD_REQUIREMENT_SECTIONS] == [
        8, 7, 3, 7, 4, 4, 5,
    ]
    assert REQUIREMENT_TOTAL == 38
    ids = [
        section["key"] + "-" + key
        for section in NERD_REQUIREMENT_SECTIONS
        for key, _label in section["items"]
    ]
    assert len(set(ids)) == REQUIREMENT_TOTAL


def test_all_supplied_personal_and_contact_fields():
    assert [label for _key, label in NERD_REQUIREMENT_SECTIONS[0]["items"]] == [
        "Title", "First Name", "Middle Name", "Surname",
        "Sex", "Date of Birth", "Marital Status", "NIN",
    ]
    assert [label for _key, label in NERD_REQUIREMENT_SECTIONS[1]["items"]] == [
        "Nationality", "State of Origin", "LGA", "Town",
        "Contact Address", "Email", "Phone Number",
    ]
    assert [label for _key, label in NERD_REQUIREMENT_SECTIONS[2]["items"]] == [
        "Name", "Phone Number", "Email",
    ]


def test_academic_supervisor_hod_and_all_attachments():
    assert [label for _key, label in NERD_REQUIREMENT_SECTIONS[3]["items"]] == [
        "Institution", "Faculty", "Department", "Programme Category",
        "Programme Type", "Matric/Reg. No.", "Course of Study",
    ]
    assert [label for _key, label in NERD_REQUIREMENT_SECTIONS[4]["items"]] == [
        "Academic Title", "Full Name", "Phone", "Email",
    ]
    assert [label for _key, label in NERD_REQUIREMENT_SECTIONS[5]["items"]] == [
        "Academic Title", "Full Name", "Phone", "Email",
    ]
    assert [label for _key, label in NERD_REQUIREMENT_SECTIONS[6]["items"]] == [
        "Passport photograph", "Picture of NIN",
        "Statement of result/Certificate", "Picture of project approval page",
        "Soft copy of complete project work",
    ]


def test_nerd_requirements_page_is_public(client):
    response = client.get("/nerd/requirements")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "NERD Requirements Checklist" in html
    assert "0 of 38 items ready" in html
    assert html.count("data-nerd-checklist-item") == 38
    assert "personal-nin" in html
    assert "documents-project" in html
    assert "/static/js/nerd_checklist.js" in html


def test_nerd_checklist_does_not_collect_identity_info_or_files(client):
    response = client.get("/nerd/requirements")
    html = response.get_data(as_text=True)
    # The normal page shell has a public search form in its HEADER.
    # Only the checklist region must be free of any identity-entry form.
    checklist = html.split('id="nerd-checklist"', 1)[1]
    assert '<form' not in checklist
    assert 'type="file"' not in checklist
    assert 'type="text"' not in checklist
    assert 'type="password"' not in checklist
    assert 'name="nin"' not in checklist
    assert "No checklist entries are sent to or saved on MyPlatoon servers" in html
    assert client.post("/nerd/requirements", data={"nin": "12345678901"}).status_code == 405


def test_links_to_official_sources_and_help(client):
    html = client.get("/nerd/requirements").get_data(as_text=True)
    assert 'href="https://databank.ned.gov.ng/register"' in html
    assert 'href="https://databank.ned.gov.ng/info/student-lecturers-sign-up"' in html
    assert 'href="https://databank.ned.gov.ng/info/nerd-receipt"' in html
    assert "09039930006" in html


def test_checklist_visible_from_nerd_and_services_hubs(client):
    assert 'href="/nerd/requirements"' in client.get("/nerd").get_data(as_text=True)
    assert 'href="/nerd/requirements"' in client.get("/services").get_data(as_text=True)
    assert 'href="/nerd/requirements"' in client.get("/").get_data(as_text=True)

"""NERD signposting stays public and makes no false official-integration claims."""


def test_nerd_page_is_public(client):
    response = client.get("/nerd")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "NERD and NYSC mobilisation" in html
    assert "https://databank.ned.gov.ng/home" in html
    assert "https://databank.ned.gov.ng/info/student-lecturers-sign-up" in html
    assert "https://databank.ned.gov.ng/info/nerd-receipt" in html
    assert "https://portal.nysc.org.ng/nysC/home" in html
    assert "09039930006" in html
    assert 'href="tel:09039930006"' in html
    assert "https://wa.me/2349039930006" in html


def test_nerd_page_discloses_independent_role_and_safety(client):
    html = client.get("/nerd").get_data(as_text=True)
    assert "not an official NERD service" in html
    assert "does not register users with NERD" in html
    assert "Never share your NERD or NYSC password" in html
    assert 'rel="noopener noreferrer"' in html


def test_nerd_page_is_linked_from_public_home(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/nerd"' in response.get_data(as_text=True)


def test_nerd_page_is_read_only(client):
    assert client.post("/nerd", data={"password": "sensitive"}).status_code == 405

"""Services directory regression tests.

CareerMirror is an external site: no user token or profile data is sent
from MyPlatoon. This tests the public rendering and accessible entry points.
"""


def test_services_hub_is_public(client):
    response = client.get("/services")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Services &amp; Career Tools" in html
    assert "CareerMirror" in html
    assert "CV and résumé preparation" in html
    assert 'href="https://mycareermirror.vercel.app/"' in html


def test_careermirror_is_marked_external_and_uses_safe_link(client):
    html = client.get("/services").get_data(as_text=True)
    assert "External service" in html
    assert "not automatically transferred" in html
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert "https://mycareermirror.vercel.app/" in html
    assert "MyPlatoon moderators" not in html


def test_services_links_ppa_and_nerd(client):
    html = client.get("/services").get_data(as_text=True)
    assert 'href="/ppas/"' in html
    assert 'href="/nerd"' in html


def test_services_discoverable_for_guests(client):
    home = client.get("/")
    assert home.status_code == 200
    assert 'href="/services"' in home.get_data(as_text=True)
    service_page = client.get("/services")
    assert service_page.status_code == 200
    assert service_page.get_data(as_text=True).count('href="/services"') >= 1


def test_services_hub_is_read_only(client):
    assert client.post("/services", data={"email": "x@y.z"}).status_code == 405


def test_services_visible_in_member_dashboard(client, member_user):
    from tests.conftest import login
    login(client, member_user.email)
    html = client.get("/profile/dashboard").get_data(as_text=True)
    assert "Career Services" in html
    assert 'href="/services"' in html

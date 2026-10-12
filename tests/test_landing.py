"""Public marketing home remains usable without database or deployment setup."""
from sqlalchemy import event


def test_landing_is_clear_and_actionable(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Your NYSC journey," in html
    assert "better connected" in html
    assert "For prospective corps members" in html
    assert 'href="/auth/register"' in html
    assert 'href="/auth/login"' in html
    assert 'href="/feed"' in html
    assert 'href="/jobs/"' in html
    assert 'href="/services"' in html
    assert 'href="/nerd/requirements"' in html
    assert 'href="/platoons/rankings"' in html
    assert "Not an official NYSC service" in html
    assert "No announcements yet" not in html
    assert "Members</div>" not in html


def test_landing_is_independent_of_branding_environment(app, client):
    original = (app.config["APP_NAME"], app.config["APP_SHORT_NAME"],
                app.config["APP_TAGLINE"], app.config["POWERED_BY"])
    try:
        app.config.update(APP_NAME="UNCONFIGURED_PRIVATE_BRAND",
                          APP_SHORT_NAME="OTHER",
                          APP_TAGLINE="SPECIAL_TEST_COPY",
                          POWERED_BY="CUSTOM_TEST_OWNER")
        page = client.get("/")
        assert page.status_code == 200
        text = page.get_data(as_text=True)
        assert "<title>MyPlatoon | Your NYSC journey, better connected</title>" in text
        for private_value in ("UNCONFIGURED_PRIVATE_BRAND", "OTHER",
                              "SPECIAL_TEST_COPY", "CUSTOM_TEST_OWNER"):
            assert private_value not in text
    finally:
        app.config.update(APP_NAME=original[0], APP_SHORT_NAME=original[1],
                          APP_TAGLINE=original[2], POWERED_BY=original[3])


def test_landing_does_not_query_database_even_when_unavailable(app, client, db):
    # This intercepts *all* actual SQL sent to SQLite. The landing can be
    # served when migration/configuration hasn't connected a database yet.
    def deny_sql(*args, **kwargs):
        raise RuntimeError("The landing must not access a database")

    with app.app_context():
        engine = db.engine
        event.listen(engine, "before_cursor_execute", deny_sql)
        try:
            response = client.get("/")
            assert response.status_code == 200
            assert b"Join the community" in response.data
        finally:
            event.remove(engine, "before_cursor_execute", deny_sql)


def test_landing_has_no_remote_js_css_or_live_counts(client):
    page = client.get("/").get_data(as_text=True)
    assert "<script" not in page
    assert "https://cdnjs." not in page
    assert "googleapis" not in page
    assert "member_count" not in page
    assert "feed_announcements" not in page
    assert "current_user" not in page
    assert 'name="viewport"' in page
    assert "prefers-reduced-motion" in page


def test_feed_stays_independent_from_marketing_hero(client):
    page = client.get("/feed")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "Community feed" in text
    assert "From mobilisation to life after service" not in text
    assert "Your NYSC journey, " not in text

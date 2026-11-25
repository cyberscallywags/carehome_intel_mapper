import httpx
import pytest

from app.api.main import app as api_app
from app.content import get_site
from app.meta import get_meta
from app.ui import main as ui


@pytest.fixture
async def ui_client(fake_store, monkeypatch):
    """UI wired to the real API app in-process (API backed by the sample care homes)."""
    api_app.state.carehomes = fake_store
    monkeypatch.setattr(
        ui,
        "api",
        lambda token=None, timeout=10: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_app),
            base_url="http://api",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ui.app), base_url="http://ui"
    ) as c:
        yield c


async def test_landing_serves_fastui_shell(ui_client):
    r = await ui_client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()


async def test_landing_is_themed_from_the_site_manifest(ui_client):
    r = await ui_client.get("/")
    assert f"--brand-primary: {get_site().theme.primary}" in r.text
    assert f"<title>{get_site().brand.name}</title>" in r.text


async def test_landing_links_the_brand_favicon_and_mark(ui_client):
    r = await ui_client.get("/")
    assert '<link rel="icon" href="/static/favicon.png">' in r.text
    assert "url('/static/mark." in r.text  # the navbar logo


@pytest.mark.parametrize("stem", ["favicon", "mark"])
async def test_static_serves_the_brand_images_sync_copied(ui_client, stem):
    url = ui.static_file(stem)
    assert url, f"run `uv run task sync`: src/app/ui/static/{stem}.* is missing"
    r = await ui_client.get(url)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")


async def test_welcome_renders_the_manifest(ui_client):
    r = await ui_client.get("/api/")
    assert r.status_code == 200
    assert get_site().welcome.sections[1].heading in r.text
    # the navbar mirrors the mobile side menu: sidebar pages plus About
    assert "/p/roadmap" in r.text and "/about" in r.text


async def test_about_promotes_the_collective(ui_client):
    r = await ui_client.get("/api/about")
    assert r.status_code == 200
    assert get_meta().organisation.name in r.text


async def test_content_page_by_slug(ui_client):
    assert "Data flow" in (await ui_client.get("/api/p/architecture")).text
    assert (await ui_client.get("/api/p/nope")).status_code == 404


async def test_navbar_lists_the_pages_then_the_map(ui_client):
    navbar = next(c for c in (await ui_client.get("/api/")).json() if c["type"] == "Navbar")
    urls = [link["onClick"]["url"] for link in navbar["startLinks"]]
    assert urls == ["/", *(f"/p/{p.slug}" for p in get_site().pages), "/map"]


async def test_welcome_opens_on_the_brand_hero(ui_client):
    [page] = [c for c in (await ui_client.get("/api/")).json() if c["type"] == "Page"]
    hero = page["components"][0]
    assert (hero["type"], hero["src"]) == ("Image", ui.static_file("hero"))
    assert hero["alt"] == get_meta().images["hero_alt"]
    # only the welcome page: About opens on its heading
    [about] = [c for c in (await ui_client.get("/api/about")).json() if c["type"] == "Page"]
    assert about["components"][0]["type"] == "Heading"


async def test_navbar_links_to_the_docs_portal(ui_client):
    r = await ui_client.get("/api/")
    assert '"url":"http://localhost:8200"' in r.text.replace(" ", "")
    assert '"target":"_blank"' in r.text.replace(" ", "")


async def test_navbar_hides_docs_without_a_docs_url(ui_client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "docs_url", None)
    assert "localhost:8200" not in (await ui_client.get("/api/")).text


# ---------------------------------------------------------------- sign-on


def demo_members():
    from app.api.auth import demo_members

    return demo_members()


async def signed_in(ui_client) -> dict:
    """Sign in through the login form; returns the first demo member."""
    from app.config import get_settings

    member = demo_members()[0]
    password = get_settings().auth_demo_password.get_secret_value()
    r = await ui_client.post("/api/login", data={"email": member.email, "password": password})
    assert r.status_code == 200, r.text
    return member


async def test_sign_on_off_shows_no_account_link(ui_client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auth_mode", "off")
    r = await ui_client.get("/api/")
    assert '"name":"account"' not in r.text.replace(" ", "")
    assert "Sign in" not in r.text
    assert "Sign-on is off" in (await ui_client.get("/api/login")).text


@pytest.mark.usefixtures("mock_sign_on")
class TestWebSignOn:
    async def test_signed_out_the_navbar_offers_sign_in(self, ui_client):
        r = await ui_client.get("/api/")
        assert '"url":"/login"' in r.text.replace(" ", "")

    async def test_login_page_has_the_form_and_the_demo_members(self, ui_client):
        r = await ui_client.get("/api/login")
        assert "ModelForm" in r.text
        for member in demo_members():
            assert f"/login/as/{member.id}" in r.text

    async def test_signing_in_goes_to_the_welcome_page(self, ui_client):
        member = demo_members()[0]
        r = await ui_client.get(f"/api/login/as/{member.id}")
        assert r.json()[0]["event"]["url"] == "/welcome"
        assert member.name in (await ui_client.get("/api/welcome")).text

    async def test_signing_in_sets_an_httponly_session_cookie(self, ui_client):
        await signed_in(ui_client)
        cookie = next(c for c in ui_client.cookies.jar if c.name == ui.SESSION_COOKIE)
        assert cookie.has_nonstandard_attr("HttpOnly")
        assert cookie.get_nonstandard_attr("SameSite", "").lower() == "lax"

    async def test_signed_in_the_navbar_names_the_member_and_opens_the_panel(self, ui_client):
        member = await signed_in(ui_client)
        r = (await ui_client.get("/api/")).text
        assert member.name in r and member.email in r
        assert '"type":"Modal"' in r.replace(" ", "")
        assert '"url":"/logout"' in r.replace(" ", "")

    async def test_a_wrong_password_is_shown_on_the_form(self, ui_client):
        member = demo_members()[0]
        r = await ui_client.post("/api/login", data={"email": member.email, "password": "no"})
        assert r.status_code == 422
        assert r.json()["detail"]["form"][0] == {
            "loc": ["password"],
            "msg": "Wrong email or password",
        }

    async def test_one_click_sign_in_as_a_demo_member(self, ui_client):
        member = demo_members()[-1]
        r = await ui_client.get(f"/api/login/as/{member.id}")
        assert r.status_code == 200
        assert member.name in (await ui_client.get("/api/")).text
        assert (await ui_client.get("/api/login/as/nobody")).status_code == 404

    async def test_signing_out_clears_the_cookie(self, ui_client):
        member = await signed_in(ui_client)
        r = await ui_client.get("/api/logout")
        assert r.json()[0]["event"] == {"url": "/welcome", "type": "go-to"}  # no query: see logout
        assert ui.SESSION_COOKIE not in ui_client.cookies
        assert member.name not in (await ui_client.get("/api/")).text


# ---------------------------------------------------------------- care home map


async def test_map_page_has_the_search_menu_and_frames_the_map(ui_client):
    r = await ui_client.get("/map")
    assert r.status_code == 200
    for field in ("name", "location", "postcode"):
        assert f'<input type="text" id="f-{field}" name="{field}"' in r.text
    assert 'id="search-menu"' in r.text and 'aria-controls="search-menu"' in r.text
    assert '<iframe title="Map of care homes' in r.text and 'src="/map/frame"' in r.text
    assert "14 care homes" in r.text
    assert "these homes are made up" in r.text


async def test_map_page_search_fills_the_form_lists_matches_and_frames_the_same_search(ui_client):
    r = await ui_client.get("/map", params={"location": "london", "rating": "Outstanding"})
    assert 'name="location" maxlength="100" autocomplete="address-level2" value="london"' in r.text
    assert 'value="Outstanding" checked' in r.text and 'value="Good" checked' not in r.text
    assert "1 care home<" in r.text
    assert "Parkside Lodge (sample)" in r.text and "Kingsmead" not in r.text
    assert 'src="/map/frame?location=london&amp;rating=Outstanding"' in r.text
    assert "location=london&amp;rating=Outstanding&amp;focus=SAMPLE-009" in r.text


async def test_map_page_escapes_what_was_searched_for(ui_client):
    r = await ui_client.get("/map", params={"name": '"><script>alert(1)</script>'})
    assert "<script>alert(1)" not in r.text


async def test_map_page_turns_a_bad_search_into_a_400(ui_client):
    assert (await ui_client.get("/map", params={"rating": "Bad"})).status_code == 400
    assert (await ui_client.get("/map/frame", params={"rating": "Bad"})).status_code == 400


async def test_map_frame_passes_on_the_api_map(ui_client):
    r = await ui_client.get("/map/frame", params={"postcode": "ls1", "focus": "SAMPLE-004"})
    assert r.status_code == 200
    assert "Oak Lodge (sample)" in r.text and "The Willows (sample)" in r.text
    assert "Harbour View" not in r.text


async def test_navbar_map_link_leaves_fastui_for_the_real_page(ui_client):
    navbar = next(c for c in (await ui_client.get("/api/")).json() if c["type"] == "Navbar")
    assert {"type": "go-to", "url": "/map"} in [x["onClick"] for x in navbar["startLinks"]]
    # FastUI then asks for /map's components and is sent to the page itself, on the address
    # the browser is using even when a proxy in front speaks https.
    r = await ui_client.get("/api/map")
    assert r.json() == [{"type": "FireEvent", "event": {"type": "go-to", "url": "http://ui/map"}}]
    r = await ui_client.get("/api/map", headers={"Referer": "https://ui/about"})
    assert r.json()[0]["event"]["url"] == "https://ui/map"
    r = await ui_client.get("/api/map", headers={"Referer": "https://elsewhere.example/"})
    assert r.json()[0]["event"]["url"] == "http://ui/map"

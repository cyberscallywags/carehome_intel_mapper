"""Real-browser checks of the UI and admin portal. Requires `task up` and
`playwright install chromium`."""

import os
import re

import pytest
from playwright.sync_api import Page, expect

from app.content import get_site
from app.meta import get_meta

pytestmark = pytest.mark.e2e

UI = os.getenv("UI_URL", "http://localhost:8080")
ADMIN = os.getenv("ADMIN_URL", "http://localhost:8501")


@pytest.fixture
def page_errors(page: Page) -> list[str]:
    """JS exceptions and console errors raised while the test runs."""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: msg.type == "error" and errors.append(msg.text))
    return errors


@pytest.fixture
def signed_in(page: Page, demo_member, demo_password):
    """Signed in through the web UI's login form; the member's name is in the navbar."""
    page.goto(f"{UI}/login")
    page.get_by_label("Email").fill(demo_member.email)
    page.get_by_label("Password").fill(demo_password)
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("link", name=demo_member.name)).to_be_visible()
    return demo_member


def test_ui_welcome_renders_the_site_manifest(page: Page, page_errors):
    site = get_site()
    page.goto(UI)
    expect(page).to_have_title(re.compile(re.escape(site.brand.name)))
    expect(page.get_by_role("heading", name=site.brand.name)).to_be_visible()
    expect(page.get_by_role("heading", name=get_site().welcome.sections[1].heading)).to_be_visible()
    hero = page.get_by_role("img", name=get_meta().images["hero_alt"])
    expect(hero).to_be_visible()
    assert hero.evaluate("img => img.complete && img.naturalWidth > 0")
    page.get_by_role("link", name="About").click()
    expect(page.get_by_role("heading", name=site.about.title)).to_be_visible()
    assert page_errors == []


def test_ui_navbar_offers_the_map_and_sign_in_but_no_items(page: Page, page_errors):
    page.goto(UI)
    nav = page.get_by_role("navigation")
    expect(nav.get_by_role("link", name="Map", exact=True)).to_be_visible()
    expect(nav.get_by_role("link", name="Items")).to_have_count(0)
    nav.get_by_role("link", name="Sign in").click()
    expect(page).to_have_url(f"{UI}/login")
    expect(page.get_by_label("Email")).to_be_visible()
    assert page_errors == []


def test_ui_wrong_password_is_shown(page: Page, demo_member):
    page.goto(f"{UI}/login")
    page.get_by_label("Email").fill(demo_member.email)
    page.get_by_label("Password").fill("not-the-password")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Wrong email or password")).to_be_visible()


def test_ui_account_panel_shows_the_member_and_signs_out(page: Page, signed_in, page_errors):
    page.get_by_role("link", name=signed_in.name).click()
    panel = page.get_by_role("dialog")
    expect(panel).to_contain_text(signed_in.email)
    expect(panel).to_contain_text(f"Role: {signed_in.role}")
    panel.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("link", name="Sign in")).to_be_visible()
    assert page_errors == []


def test_ui_one_click_demo_sign_in(page: Page, demo_admin):
    page.goto(f"{UI}/login")
    page.get_by_role("button", name=f"{demo_admin.name} ({demo_admin.role})").click()
    expect(page.get_by_role("link", name=demo_admin.name)).to_be_visible()


def test_ui_stays_signed_in_on_the_map_page_and_back(page: Page, signed_in, page_errors):
    """The map is a page of its own outside FastUI; the session cookie survives the round trip."""
    page.get_by_role("link", name="Map", exact=True).click()
    expect(page.locator("#search-menu")).to_be_visible()
    page.get_by_role("link", name=get_site().welcome.title).click()
    expect(page.get_by_role("link", name=signed_in.name)).to_be_visible()
    assert page_errors == []


def sign_in_to_admin(page: Page, email: str, password: str) -> None:
    page.goto(ADMIN)
    main = page.get_by_test_id("stMain")
    main.get_by_label("Email").fill(email)
    main.get_by_role("textbox", name="Password").fill(password)
    main.get_by_role("button", name="Sign in").click()


def test_admin_turns_away_members_who_are_not_admins(page: Page, demo_member, demo_password):
    sign_in_to_admin(page, demo_member.email, demo_password)
    expect(page.get_by_text("for admin members only")).to_be_visible(timeout=30_000)
    expect(page.get_by_test_id("stDataFrame")).to_have_count(0)


def test_admin_shows_healthy_stack(page: Page, demo_admin, demo_password):
    sign_in_to_admin(page, demo_admin.email, demo_password)
    main = page.get_by_test_id("stMain")
    expect(main.get_by_role("heading", name=f"{get_meta().name} admin")).to_be_visible(
        timeout=30_000
    )
    expect(main.get_by_text('"neo4j":true')).to_be_visible()
    expect(main.get_by_text('"edition":"')).to_be_visible()  # community or enterprise
    expect(main.get_by_role("heading", name="Care homes")).to_be_visible()
    expect(page.get_by_test_id("stDataFrame")).to_be_visible()  # the care home table
    expect(page.get_by_test_id("stAlert")).to_have_count(0)


# ---------------------------------------------------------------- care home map


def test_map_search_menu_narrows_the_map(page: Page, page_errors):
    page.goto(f"{UI}/map")
    count = page.get_by_test_id("count")
    total = int(re.sub(r"\D", "", count.inner_text()))
    assert total > 0
    frame = page.frame_locator("iframe")
    expect(frame.locator(".ch-legend")).to_contain_text("Latest CQC rating")
    expect(frame.locator(".leaflet-marker-icon").first).to_be_visible()

    first = page.get_by_test_id("results").get_by_role("link").first
    name = first.inner_text()
    page.get_by_label("Name").fill(name)
    page.get_by_role("button", name="Search").click()
    expect(page).to_have_url(re.compile(r"/map\?.*name="))
    assert int(re.sub(r"\D", "", count.inner_text())) < total or total == 1

    page.get_by_test_id("results").get_by_role("link", name=name).first.click()
    expect(page.frame_locator("iframe").locator(".ch-popup")).to_contain_text(name)
    assert page_errors == []


def test_map_search_menu_slides_over_the_map_on_a_phone(page: Page):
    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(f"{UI}/map")
    menu = page.locator("#search-menu")
    expect(menu).not_to_be_in_viewport()
    page.get_by_role("button", name="Search").first.click()
    expect(menu).to_be_in_viewport()
    page.keyboard.press("Escape")
    expect(menu).not_to_be_in_viewport()


def test_navbar_reaches_the_map(page: Page):
    page.goto(UI)
    page.get_by_role("link", name="Map", exact=True).click()
    expect(page.locator("#search-menu")).to_be_visible()
    expect(page).to_have_url(f"{UI}/map")

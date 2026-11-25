"""Real-browser checks of the Ionic mobile app on an emulated phone. Requires `task up`
and `playwright install chromium`."""

import os
import re

import pytest
from playwright.sync_api import Page, Playwright, expect

from app.content import get_site

pytestmark = pytest.mark.e2e

MOBILE = os.getenv("MOBILE_URL", "http://localhost:8100")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, playwright: Playwright) -> dict:
    """Every test in this module runs as a touch-screen Android phone."""
    return {**browser_context_args, **playwright.devices["Pixel 7"]}


@pytest.fixture
def page_errors(page: Page) -> list[str]:
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: msg.type == "error" and errors.append(msg.text))
    return errors


def test_mobile_opens_on_welcome_from_the_site_manifest(page: Page, page_errors):
    site = get_site()
    page.goto(MOBILE)
    expect(page).to_have_title(f"{site.welcome.title} · {site.brand.name}")
    expect(page).to_have_url(re.compile(r"/welcome$"))
    expect(page.get_by_test_id("page-welcome")).to_contain_text(site.brand.name)
    expect(page.get_by_text(get_site().welcome.sections[1].heading)).to_be_visible()
    # brand colour from GET /site is applied to Ionic's theme
    primary = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--ion-color-primary')"
    )
    assert primary.strip() == site.theme.primary
    assert page.evaluate("matchMedia('(pointer: coarse)').matches")  # a phone, not a desktop
    assert page_errors == []


def test_mobile_welcome_shows_the_brand_hero(page: Page):
    page.goto(f"{MOBILE}/welcome")
    hero = page.locator("img.hero-image")
    expect(hero).to_be_visible()
    assert hero.get_attribute("alt")
    assert hero.evaluate("img => img.complete && img.naturalWidth > 0")


def test_mobile_side_menu_reaches_project_pages_and_about(page: Page, page_errors):
    page.goto(f"{MOBILE}/welcome")
    page.locator("ion-menu-button").first.tap()
    page.get_by_test_id("menu").get_by_text("Roadmap").tap()
    expect(page.get_by_test_id("page-roadmap")).to_be_visible()
    page.locator("ion-menu-button").last.tap()
    site = get_site()
    page.locator("ion-menu ion-footer").get_by_text(site.about.title).tap()
    expect(page.get_by_test_id("page-about")).to_contain_text(site.about.title)
    expect(page.locator("app-content").last).to_contain_text(site.brand.collective)
    assert page_errors == []


def test_mobile_side_menu_offers_the_map_but_no_items(page: Page, page_errors):
    page.goto(f"{MOBILE}/welcome")
    page.locator("ion-menu-button").first.tap()
    menu = page.get_by_test_id("menu")
    expect(menu.get_by_text("Items")).to_have_count(0)
    menu.get_by_text("Map", exact=True).tap()
    expect(page).to_have_url(re.compile(r"/map$"))
    expect(page).to_have_title(f"Map · {get_site().brand.name}")
    assert page_errors == []


def test_mobile_removed_items_address_falls_back_to_welcome(page: Page):
    page.goto(f"{MOBILE}/items")
    expect(page).to_have_url(re.compile(r"/welcome$"))


def sign_in(page: Page, email: str, password: str, then: str = "/account") -> None:
    """Through the app's sign-in page, which returns to `then`."""
    page.goto(f"{MOBILE}/sign-in?returnUrl={then}")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").tap()
    expect(page).to_have_url(re.compile(rf"{re.escape(then)}$"))


def test_mobile_account_page_asks_the_signed_out_to_sign_in(
    page: Page, demo_member, demo_password, page_errors
):
    # The guard reads the sign-on mode from the site manifest, which the app caches on its
    # first visit; before that it cannot tell that sign-on is on.
    page.goto(f"{MOBILE}/welcome")
    expect(page.get_by_test_id("sign-on")).to_be_attached()
    page.goto(f"{MOBILE}/account")
    expect(page).to_have_url(re.compile(r"/sign-in\?returnUrl=%2Faccount$"))
    page.get_by_label("Email").fill(demo_member.email)
    page.get_by_label("Password").fill(demo_password)
    page.get_by_role("button", name="Sign in").tap()
    expect(page).to_have_url(re.compile(r"/account$"))
    account = page.get_by_test_id("account")
    expect(account).to_contain_text(demo_member.name)
    expect(account).to_contain_text(demo_member.role)
    assert page_errors == []


def test_mobile_account_menu_shows_the_member_and_signs_out(
    page: Page, demo_member, demo_password, page_errors
):
    sign_in(page, demo_member.email, demo_password)
    page.locator("app-account [data-testid=account-button]").tap()
    menu = page.get_by_test_id("account-menu")
    expect(menu).to_contain_text(demo_member.email)
    menu.get_by_test_id("sign-out").tap()
    expect(page).to_have_url(re.compile(r"/welcome$"))
    expect(page.locator("app-content [data-testid=account-button]")).to_contain_text("Sign in")
    assert page_errors == []


def test_mobile_wrong_password_is_shown_and_does_not_sign_in(page: Page, demo_member):
    page.goto(f"{MOBILE}/sign-in")
    page.get_by_label("Email").fill(demo_member.email)
    page.get_by_label("Password").fill("not-the-password")
    page.get_by_role("button", name="Sign in").tap()
    expect(page.get_by_text("Wrong email or password")).to_be_visible()
    expect(page).to_have_url(re.compile(r"/sign-in"))


# ---------------------------------------------------------------- care home map


def test_map_page_searches_from_the_side_menu(page: Page, page_errors):
    page.goto(f"{MOBILE}/map")
    frame = page.frame_locator("iframe.map")
    expect(frame.locator(".leaflet-marker-icon").first).to_be_visible()
    menu = page.get_by_test_id("search-menu")
    expect(menu).not_to_be_in_viewport()

    page.get_by_test_id("open-search").tap()
    expect(menu).to_be_in_viewport()
    first = page.get_by_test_id("results").locator("ion-item").first
    name = first.locator("h3").inner_text()
    page.get_by_label("Name").fill(name)
    page.get_by_test_id("search").tap()
    expect(menu).not_to_be_in_viewport()
    expect(page.locator("iframe.map")).to_have_attribute("src", re.compile(r"carehomes/map\?name="))

    page.get_by_test_id("open-search").tap()
    page.get_by_test_id("results").get_by_text(name).first.tap()
    expect(page.frame_locator("iframe.map").locator(".ch-popup")).to_contain_text(name)
    assert page_errors == []

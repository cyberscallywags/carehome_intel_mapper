"""End-to-end checks across every container. Requires `task up` (or the CI compose step)."""

import html
import os
from pathlib import Path

import httpx
import pytest
from neo4j import GraphDatabase

pytestmark = pytest.mark.integration


def neo4j_image() -> str:
    env_test = Path(__file__).parents[2] / ".env.test"
    lines = [line for line in env_test.read_text().splitlines() if line.startswith("NEO4J_IMAGE=")]
    return os.getenv("NEO4J_IMAGE") or (lines[0].split("=", 1)[1] if lines else "")


API = os.getenv("API_URL", "http://localhost:8000")
UI = os.getenv("UI_URL", "http://localhost:8080")
ADMIN = os.getenv("ADMIN_URL", "http://localhost:8501")
MOBILE = os.getenv("MOBILE_URL", "http://localhost:8100")
DOCS = os.getenv("DOCS_URL", "http://localhost:8200")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "sgaffald-test-only")
DEMO_PASSWORD = os.getenv("AUTH_DEMO_PASSWORD", "demo")
# Community unless NEO4J_IMAGE (the environment, else .env.test) names an Enterprise image
NEO4J_EDITION = "enterprise" if "enterprise" in neo4j_image() else "community"


@pytest.fixture(scope="module")
def member() -> dict:
    """Who asks the agent: the first demo member when sign-on is mock, else the local member."""
    auth = httpx.get(f"{API}/site").json()["auth"]
    if auth["mode"] != "mock":
        return {"member": {"id": "local"}, "headers": {}}
    first = auth["demo_users"][0]
    login = {"email": first["email"], "password": DEMO_PASSWORD}
    session = httpx.post(f"{API}/auth/login", json=login).raise_for_status().json()
    return {**session, "headers": {"Authorization": f"Bearer {session['token']}"}}


def test_api_sees_neo4j():
    body = httpx.get(f"{API}/health").json()
    assert body["neo4j"] is True, body


def test_the_agent_needs_a_token_when_sign_on_is_mock(member):
    if not member["headers"]:
        pytest.skip("sign-on is off in this stack")
    assert httpx.post(f"{API}/ask", json={"question": "Any homes?"}).status_code == 401
    assert httpx.get(f"{API}/carehomes", params={"limit": 1}).status_code == 200  # reads are public


def test_sign_on_reaches_the_api_through_the_mobile_proxy(member):
    if not member["headers"]:
        pytest.skip("sign-on is off in this stack")
    me = httpx.get(f"{MOBILE}/api/auth/me", headers=member["headers"])
    assert me.json() == member["member"]


def test_neo4j_edition_matches_the_image():
    with GraphDatabase.driver(NEO4J_URI, auth=("neo4j", NEO4J_PASSWORD)) as driver:
        records, _, _ = driver.execute_query("CALL dbms.components() YIELD edition RETURN edition")
    assert records[0]["edition"] == NEO4J_EDITION


def test_ui_lists_care_homes_from_the_api():
    assert httpx.get(f"{UI}/").status_code == 200
    home = httpx.get(f"{API}/carehomes", params={"limit": 1}, timeout=30).json()["items"][0]
    page = httpx.get(f"{UI}/map", params={"name": home["name"]}, timeout=30).text
    assert home["name"] in html.unescape(page)


def test_agent_answers_about_care_homes(member):
    question = {"question": "How many care homes are there?"}
    r = httpx.post(f"{API}/ask", json=question, headers=member["headers"], timeout=60)
    assert r.status_code == 200 and r.json()["answer"]


def test_admin_is_up():
    assert httpx.get(f"{ADMIN}/_stcore/health").text == "ok"


def test_mobile_serves_app():
    r = httpx.get(f"{MOBILE}/map")  # deep link falls back to the SPA shell
    assert r.status_code == 200 and "<app-root>" in r.text


def test_web_and_mobile_share_one_site_manifest():
    site = httpx.get(f"{API}/site").json()
    assert httpx.get(f"{MOBILE}/api/site").json() == site
    assert site["theme"]["primary"] in httpx.get(f"{UI}/").text


def test_mobile_proxies_api_to_neo4j():
    assert httpx.get(f"{MOBILE}/api/health").json()["neo4j"] is True
    params = {"limit": 5}
    direct = httpx.get(f"{API}/carehomes", params=params, timeout=30).json()
    assert httpx.get(f"{MOBILE}/api/carehomes", params=params, timeout=30).json() == direct


def test_api_allows_native_app_origin():
    r = httpx.options(
        f"{API}/ask",
        headers={
            "Origin": "capacitor://localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "capacitor://localhost"


def test_docs_serves_portal_and_manual():
    assert httpx.get(f"{DOCS}/healthz").json() == {"status": "ok"}
    portal = httpx.get(f"{DOCS}/")
    assert portal.status_code == 200 and "assets/brand/" in portal.text
    # /manual/ redirects to the Sphinx home page, which exists
    assert "url=manual.html" in httpx.get(f"{DOCS}/manual/").text
    assert httpx.get(f"{DOCS}/manual/manual.html").status_code == 200
    assert httpx.get(f"{DOCS}/assets/brand/favicon.png").status_code == 200


def test_docs_reference_is_generated_from_the_running_code():
    # the image ran app.docgen: every API route is documented on both sites
    paths = httpx.get(f"{API}/openapi.json").json()["paths"]
    portal = httpx.get(f"{DOCS}/reference/http-api/").text
    manual = httpx.get(f"{DOCS}/manual/reference/http-api.html").text
    for path in paths:
        assert path in portal and path in manual


def test_apps_link_to_the_docs():
    assert httpx.get(f"{API}/site").json()["docs_url"] == DOCS
    assert DOCS in httpx.get(f"{UI}/api/").text


# ---------------------------------------------------------------- care homes


def test_care_homes_are_stored_in_neo4j_and_searchable():
    """The API loaded care homes into the graph at start-up (the made-up sample unless
    data/carehomes.json exists), and the search runs in Neo4j."""
    everything = httpx.get(f"{API}/carehomes", params={"limit": 1}, timeout=30).json()
    assert everything["total"] > 0
    assert everything["dataset"]["count"] == everything["total"]
    with GraphDatabase.driver(NEO4J_URI, auth=("neo4j", NEO4J_PASSWORD)) as driver:
        records, _, _ = driver.execute_query("MATCH (c:CareHome) RETURN count(c) AS n")
    assert records[0]["n"] == everything["total"]

    home = everything["items"][0]
    word = home["name"].split()[0]
    outward = home["postcode"].split()[0]
    for search in (
        {"name": word.upper()},
        {"postcode": outward.lower()},
        {"rating": home["rating"]},
    ):
        found = httpx.get(f"{API}/carehomes", params={**search, "limit": 500}, timeout=30).json()
        assert home["location_id"] in [h["location_id"] for h in found["items"]], search
    assert httpx.get(f"{API}/carehomes/{home['location_id']}", timeout=30).json() == home
    assert httpx.get(f"{API}/carehomes", params={"name": "zzzz-no-such-home"}).json()["total"] == 0


@pytest.mark.parametrize("base", ["UI", "MOBILE"])
def test_both_frontends_serve_the_care_home_map(base):
    """The web UI passes the API's map on at /map/frame; the mobile image proxies it at /api."""
    url = f"{UI}/map/frame" if base == "UI" else f"{MOBILE}/api/carehomes/map"
    r = httpx.get(url, params={"focus": "none"}, timeout=60)
    assert r.status_code == 200
    assert "Latest CQC rating" in r.text and "markerClusterGroup" in r.text

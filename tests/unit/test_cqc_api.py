"""The CQC API client, the ingest command and the live-record endpoint, against a stand-in
for CQC's API (no network)."""

import httpx
import pytest
from pydantic import SecretStr
from test_cqc_directory import HEADINGS, cell, directory_row, write_ods
from test_cqc_models import LOCATION

from app.api.main import app
from app.carehomes import ingest, routes
from app.carehomes.cqc_api import KEY_HEADER, CqcApi, CqcApiError
from app.carehomes.store import read_snapshot
from app.config import Settings
from app.meta import get_meta

BASE = "https://cqc.test/public/v1"
KEY = "test-subscription-key"


class FakeCqc:
    """Three locations (one not a care home) from one provider, two per list page. Counts
    requests, checks the key, and can ask the client to slow down."""

    def __init__(self) -> None:
        self.locations = {
            "1-101": LOCATION,
            "1-102": LOCATION | {"locationId": "1-102", "name": "Ail Example"},
            "1-103": LOCATION | {"locationId": "1-103", "careHome": "N"},
        }
        self.requests: list[httpx.Request] = []
        self.throttle = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get(KEY_HEADER) != KEY:
            return httpx.Response(401, json={"message": "Access denied due to invalid key"})
        if self.throttle:
            self.throttle -= 1
            return httpx.Response(429, headers={"Retry-After": "3"})
        path = request.url.path.removeprefix("/public/v1")
        if path == "/locations":
            assert request.url.params["careHome"] == "Y"
            page = int(request.url.params["page"])
            ids = sorted(self.locations)[(page - 1) * 2 : page * 2]
            return httpx.Response(
                200,
                json={
                    "total": 3,
                    "page": page,
                    "totalPages": 2,
                    "locations": [{"locationId": i, "locationName": "x"} for i in ids],
                },
            )
        if path.startswith("/locations/"):
            found = self.locations.get(path.rsplit("/", 1)[-1])
            return httpx.Response(200, json=found) if found else httpx.Response(404, json={})
        if path == "/providers/1-9":
            return httpx.Response(200, json={"providerId": "1-9", "name": "Example Care Ltd"})
        return httpx.Response(404, json={})


@pytest.fixture
def cqc() -> FakeCqc:
    return FakeCqc()


def client(cqc: FakeCqc, key: str = KEY, **options) -> CqcApi:
    return CqcApi(BASE, key, transport=httpx.MockTransport(cqc), **options)


async def test_reads_every_care_home_with_who_runs_it(cqc):
    stages = []
    async with client(cqc, partner_code="ScallywagsTest") as api:
        homes = await api.care_homes(progress=lambda *step: stages.append(step))
    assert [(h.location_id, h.name, h.provider_name) for h in homes] == [
        ("1-101", "Ty Example", "Example Care Ltd"),
        ("1-102", "Ail Example", "Example Care Ltd"),
    ]
    assert homes[0].rating_well_led == "Requires improvement"
    paths = [r.url.path.removeprefix("/public/v1") for r in cqc.requests]
    assert paths.count("/locations") == 2 and paths.count("/providers/1-9") == 1
    assert all(r.url.params["partnerCode"] == "ScallywagsTest" for r in cqc.requests)
    assert stages == [("care homes", 3, 3), ("providers", 1, 1)]


async def test_waits_as_long_as_the_api_asks_then_retries(cqc):
    waits = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    cqc.throttle = 2
    async with client(cqc, sleep=sleep) as api:
        assert (await api.location("1-101")).name == "Ty Example"
    assert waits == [3.0, 3.0]


async def test_a_refused_key_says_where_to_find_the_right_one(cqc):
    async with client(cqc, key="wrong") as api:
        with pytest.raises(CqcApiError, match="CQC_API_KEY.*api-portal.service.cqc.org.uk"):
            await api.location("1-101")


# ---------------------------------------------------------------- the ingest command


def settings(**changes) -> Settings:
    return Settings(cqc_api_url=BASE, cqc_api_key=SecretStr(KEY), **changes)


async def test_ingest_from_the_api(cqc):
    snapshot = await ingest.from_api(settings(), transport=httpx.MockTransport(cqc))
    assert (snapshot.dataset.source, snapshot.dataset.name, snapshot.dataset.count) == (
        "cqc-api",
        BASE,
        2,
    )
    with pytest.raises(ingest.IngestError, match="Set CQC_API_KEY"):
        await ingest.from_api(Settings(cqc_api_key=None))


def directory_file(path) -> None:
    rows = [HEADINGS, directory_row(), directory_row(**{"Location ID": "1-102", "Care home?": "N"})]
    write_ods(path, {"HSCA_Active_Locations": ["".join(cell(v) for v in row) for row in rows]})


def test_ingest_command_writes_the_snapshot_from_a_spreadsheet(tmp_path, capsys):
    source = tmp_path / "2_November_2026_HSCA_Active_Locations.ods"
    directory_file(source)
    out = tmp_path / "data" / "carehomes.json"
    assert ingest.main([str(source), "--out", str(out)]) == 0
    snapshot = read_snapshot(out)
    assert [h.name for h in snapshot.homes] == ["Ty Example"]
    assert (snapshot.dataset.source, str(snapshot.dataset.as_of)) == ("cqc-directory", "2026-11-02")
    printed = capsys.readouterr().out
    assert "2 locations, 1 of them care homes" in printed
    assert "Requires improvement 1" in printed and "Open Government Licence" in printed


def test_ingest_command_explains_a_wrong_file(tmp_path, capsys):
    wrong = tmp_path / "CQC_directory.csv"
    wrong.write_text("Name,Postcode\nTy Example,BS1 9ZZ\n")
    out = tmp_path / "carehomes.json"
    assert ingest.main([str(wrong), "--out", str(out)]) == 1
    assert "care directory with filters" in capsys.readouterr().err
    assert not out.exists()
    assert ingest.main([str(tmp_path / "missing.ods"), "--out", str(out)]) == 1


def cqc_site(tmp_path, status: int = 200):
    source = tmp_path / "source.ods"
    directory_file(source)
    fetched = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        assert request.headers["User-Agent"].startswith(f"{get_meta().slug}/")
        if request.url.path.endswith("using-cqc-data"):
            link = "/system/files/2026-11/2_November_2026_HSCA_Active_Locations.ods"
            return httpx.Response(200, text=f'<a href="{link}">Care directory with filters</a>')
        return httpx.Response(status, content=source.read_bytes() if status == 200 else b"")

    return httpx.MockTransport(handler), fetched


def test_download_finds_the_directory_and_fetches_it_once(tmp_path):
    transport, fetched = cqc_site(tmp_path)
    page = "https://www.cqc.test/about-us/transparency/using-cqc-data"
    path = ingest.download_directory(page, tmp_path / "data", transport)
    assert path.name == "2_November_2026_HSCA_Active_Locations.ods"
    assert fetched[1] == "https://www.cqc.test/system/files/2026-11/" + path.name
    assert ingest.from_directory(path)[0].dataset.count == 1
    ingest.download_directory(page, tmp_path / "data", transport)
    assert len(fetched) == 3  # the page again, but not the file


def test_download_refused_says_how_to_do_it_by_hand(tmp_path):
    transport, _ = cqc_site(tmp_path, status=403)
    page = "https://www.cqc.test/about-us/transparency/using-cqc-data"
    with pytest.raises(ingest.IngestError, match="HTTP 403.*in a browser.*task ingest <the file>"):
        ingest.download_directory(page, tmp_path / "data", transport)
    assert not list((tmp_path / "data").glob("*.ods"))


# ---------------------------------------------------------------- the live record endpoint


@pytest.fixture
async def api_client(cqc):
    app.dependency_overrides[routes.get_cqc_api] = lambda: client(cqc)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as c:
        yield c
    app.dependency_overrides.clear()


async def test_live_cqc_record(api_client):
    r = await api_client.get("/carehomes/1-101/cqc")
    assert r.status_code == 200
    body = r.json()
    assert body["current_ratings"]["overall"]["key_question_ratings"][0] == {
        "name": "Safe",
        "rating": "Requires improvement",
        "report_date": "2025-06-20",
        "report_link_id": "abc",
        "organisation_id": None,
    }
    assert body["historic_ratings"][0]["overall"]["rating"] == "Good"
    assert (await api_client.get("/carehomes/1-999/cqc")).status_code == 404
    assert (await api_client.get("/carehomes/bad id!/cqc")).status_code == 422


async def test_live_cqc_record_needs_a_key_on_the_server(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: Settings(cqc_api_key=None))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as c:
        r = await c.get("/carehomes/1-101/cqc")
    assert r.status_code == 503 and "CQC_API_KEY" in r.json()["detail"]

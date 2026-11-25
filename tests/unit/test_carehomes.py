"""Care homes: the search, the snapshot loaded at start-up, the map and the API routes."""

from datetime import date

import httpx
import pytest

from app.api.main import app
from app.carehomes.mapview import render_map
from app.carehomes.store import (
    MemoryCareHomeStore,
    Query,
    Snapshot,
    load_startup_data,
    read_snapshot,
    sample_snapshot,
    write_snapshot,
)
from app.models import CareHome, CareHomeDataset


def home(location_id: str = "1-1", **fields) -> CareHome:
    defaults = {"name": "Ty Example", "latitude": 51.7, "longitude": -5.0, "postcode": "SA73 2JA"}
    return CareHome(location_id=location_id, **(defaults | fields))


# ---------------------------------------------------------------- the store


@pytest.fixture
async def store() -> MemoryCareHomeStore:
    memory = MemoryCareHomeStore()
    await memory.replace(sample_snapshot())
    return memory


async def names(store, **search) -> list[str]:
    _, found = await store.search(Query.of(**search))
    return [h.name.removesuffix(" (sample)") for h in found]


async def test_search_by_name_location_postcode_and_rating(store):
    assert await names(store, name="house RIVERSIDE") == ["Riverside House"]
    assert await names(store, location="london") == ["Kingsmead", "Parkside Lodge"]
    assert await names(store, location="yorkshire leeds") == ["Oak Lodge"]
    assert await names(store, postcode="se1") == ["Kingsmead"]
    assert await names(store, postcode=" s1 9") == ["Beacon Court"]
    assert await names(store, location="london", ratings=["Outstanding"]) == ["Parkside Lodge"]
    assert await names(store, name="nowhere") == []


async def test_search_pages_in_name_order(store):
    total, page = await store.search(Query.of(), limit=3, offset=2)
    assert total == 14
    assert [h.name for h in page] == [
        "Castle Rise (sample)",
        "Cedar Grange (sample)",
        "Harbour View (sample)",
    ]


async def test_startup_loads_the_sample_until_a_snapshot_exists(tmp_path):
    memory = MemoryCareHomeStore()
    path = tmp_path / "carehomes.json"
    assert (await load_startup_data(memory, path)).source == "sample"

    dataset = CareHomeDataset(source="cqc-directory", name="directory.ods", as_of=date(2026, 11, 2))
    write_snapshot(path, Snapshot(dataset=dataset, homes=[home(), home("1-2", name="Ail")]))
    assert read_snapshot(path).dataset.name == "directory.ods"
    loaded = await load_startup_data(memory, path)
    assert (loaded.source, loaded.count) == ("cqc-directory", 2)
    assert [h.name for h in memory.homes] == ["Ail", "Ty Example"]

    held = memory.homes
    await load_startup_data(memory, path)  # the same snapshot is not loaded twice
    assert memory.homes is held


async def test_startup_survives_a_broken_snapshot(tmp_path):
    path = tmp_path / "carehomes.json"
    path.write_text("{not json")
    assert await load_startup_data(MemoryCareHomeStore(), path) is None


# ---------------------------------------------------------------- the map


def test_map_has_a_marker_row_and_a_key_for_every_rating():
    snapshot = sample_snapshot()
    html = render_map(snapshot.homes, snapshot.dataset)
    assert '"Harbour View (sample)"' in html
    assert "Outstanding (3)" in html and "Not rated (2)" in html
    assert "Sample data: these homes are made up" in html
    assert "markerClusterGroup" in html


def test_map_text_cannot_become_markup():
    evil = home(name="</script><script>alert(1)</script>")
    html = render_map([evil], focus=evil)
    assert "<script>alert(1)" not in html
    assert "openPopup" in html


def test_map_of_nothing_says_so():
    html = render_map([], CareHomeDataset(source="cqc-directory", name="x.ods"))
    assert "No care homes match this search" in html
    assert "made up" not in html


# ---------------------------------------------------------------- the API


@pytest.fixture
async def client(store):
    app.state.carehomes = store  # ASGITransport skips the lifespan
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as c:
        yield c


async def test_api_search(client):
    r = await client.get("/carehomes", params={"location": "london", "limit": 1})
    body = r.json()
    assert r.status_code == 200
    assert (body["total"], [h["name"] for h in body["items"]]) == (2, ["Kingsmead (sample)"])
    assert body["dataset"]["source"] == "sample"
    r = await client.get("/carehomes", params=[("rating", "Good"), ("rating", "Inadequate")])
    assert r.json()["total"] == 7


async def test_api_rejects_an_unknown_rating(client):
    assert (await client.get("/carehomes", params={"rating": "Bad"})).status_code == 422


async def test_api_one_home(client):
    assert (await client.get("/carehomes/SAMPLE-001")).json()["rating"] == "Outstanding"
    assert (await client.get("/carehomes/none")).status_code == 404


async def test_api_map_is_html_for_the_search(client):
    r = await client.get("/carehomes/map", params={"postcode": "LS1", "focus": "SAMPLE-004"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Oak Lodge (sample)" in r.text
    assert "The Willows (sample)" in r.text  # the focused home, though outside the search
    assert "Harbour View" not in r.text

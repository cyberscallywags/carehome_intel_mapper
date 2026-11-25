"""The API's care home endpoints: search, one home, and the map both frontends frame."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse

from app.carehomes import store as storage
from app.carehomes.cqc_api import CqcApi, CqcApiError
from app.carehomes.cqc_models import CqcLocation
from app.carehomes.mapview import render_map
from app.carehomes.store import CareHomeStore
from app.config import get_settings
from app.models import CareHome, CareHomePage, Rating

router = APIRouter(prefix="/carehomes", tags=["care homes"])


def get_store(request: Request) -> CareHomeStore:
    return request.app.state.carehomes


Store = Annotated[CareHomeStore, Depends(get_store)]


def search_query(
    name: Annotated[
        str, Query(max_length=100, description="Words that must all appear in the home's name.")
    ] = "",
    location: Annotated[
        str,
        Query(
            max_length=100,
            description="Words that must all appear in its address, town, county, local "
            "authority or region.",
        ),
    ] = "",
    postcode: Annotated[
        str,
        Query(max_length=10, description="Start of the postcode, e.g. `SA73` or `SA73 2`."),
    ] = "",
    rating: Annotated[
        list[Rating] | None, Query(description="Only these ratings; repeat for several.")
    ] = None,
) -> storage.Query:
    return storage.Query.of(name, location, postcode, rating or [])


Search = Annotated[storage.Query, Depends(search_query)]


@router.get("", response_model=CareHomePage)
async def search_care_homes(
    store: Store,
    query: Search,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CareHomePage:
    """Care homes matching every part of the search that is given, in name order, with the
    total number of matches and where the data came from. No search lists every home."""
    total, items = await store.search(query, limit=limit, offset=offset)
    return CareHomePage(total=total, items=items, dataset=await store.dataset())


@router.get("/map", response_class=HTMLResponse)
async def care_home_map(
    store: Store,
    query: Search,
    focus: Annotated[
        str, Query(max_length=40, description="`location_id` of a home to centre on and open.")
    ] = "",
) -> HTMLResponse:
    """An HTML map (Folium) of every home matching the search, coloured by latest CQC rating;
    made to be shown in a frame by the web UI and the mobile app."""
    _, homes = await store.search(query)
    focused = await store.get(focus) if focus else None
    return HTMLResponse(render_map(homes, await store.dataset(), focused))


@router.get("/{location_id}", response_model=CareHome)
async def get_care_home(location_id: str, store: Store) -> CareHome:
    """One care home by its CQC location id."""
    if (home := await store.get(location_id)) is None:
        raise HTTPException(status_code=404, detail="No care home with that location id")
    return home


def get_cqc_api() -> CqcApi:
    """A client for CQC's API, for the one endpoint that reads it live."""
    settings = get_settings()
    if settings.cqc_api_key is None:
        raise HTTPException(
            status_code=503, detail="CQC_API_KEY is not set, so CQC's API cannot be asked"
        )
    return CqcApi(
        settings.cqc_api_url, settings.cqc_api_key.get_secret_value(), settings.cqc_partner_code
    )


@router.get("/{location_id}/cqc", response_model=CqcLocation, response_model_by_alias=False)
async def get_cqc_record(
    location_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,40}$")],
    cqc: Annotated[CqcApi, Depends(get_cqc_api)],
) -> CqcLocation:
    """CQC's full, current record for a location, read from its API as you ask: every rating
    with its history, the reports, regulated activities and assessments. Needs `CQC_API_KEY`
    on the server (503 without it)."""
    try:
        async with cqc:
            return await cqc.location(location_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="CQC has no such location") from None
        raise HTTPException(status_code=502, detail="CQC's API returned an error") from None
    except CqcApiError, httpx.HTTPError:
        raise HTTPException(status_code=502, detail="CQC's API could not be read") from None

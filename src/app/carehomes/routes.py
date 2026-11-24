"""The API's care home endpoints: search, one home, and the map both frontends frame."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.carehomes import store as storage
from app.carehomes.mapview import render_map
from app.carehomes.store import CareHomeStore
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

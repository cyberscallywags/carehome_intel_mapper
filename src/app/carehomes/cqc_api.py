"""Client for the CQC syndication API (https://api-portal.service.cqc.org.uk).

CQC's guide: register on the API portal, request a subscription key, and send it on every
request as the `Ocp-Apim-Subscription-Key` header; without a valid key the API answers 401.
`GET /locations?careHome=Y` pages through location ids, and `GET /locations/{id}` returns one
location (app.carehomes.cqc_models.CqcLocation), which `care_home_from` maps onto our model.
The list has no coordinates or ratings, so a full import is one request per home; the
spreadsheet (app.carehomes.directory) is the quicker route for everything at once.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from app.carehomes.cqc_models import (
    CqcLocation,
    CqcProvider,
    LocationPage,
    care_home_from,
)
from app.models import CareHome

KEY_HEADER = "Ocp-Apim-Subscription-Key"
PAGE_SIZE = 1000
RETRIES = 5


class CqcApiError(RuntimeError):
    """The API refused a request; the message says what to do about it."""


class CqcApi:
    """`async with CqcApi(base_url, key) as api:` then `api.care_home_ids()` and
    `api.location(id)`."""

    def __init__(
        self,
        base_url: str,
        key: str,
        partner_code: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.params = {"partnerCode": partner_code} if partner_code else {}
        self.sleep = sleep
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={KEY_HEADER: key, "Accept": "application/json"},
            timeout=30,
            transport=transport,
        )

    async def __aenter__(self) -> CqcApi:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.client.aclose()

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        """GET one resource, waiting and retrying when the API asks us to slow down."""
        for attempt in range(RETRIES):
            resp = await self.client.get(path, params={**self.params, **params})
            if resp.status_code in {429, 502, 503, 504} and attempt < RETRIES - 1:
                wait = resp.headers.get("Retry-After", "")
                await self.sleep(float(wait) if wait.isdigit() else 2.0**attempt)
                continue
            if resp.status_code in {401, 403}:
                raise CqcApiError(
                    "The CQC API refused the subscription key (HTTP "
                    f"{resp.status_code}). Check CQC_API_KEY against the key on your profile "
                    "page at https://api-portal.service.cqc.org.uk"
                )
            resp.raise_for_status()
            return resp.json()
        raise CqcApiError(f"The CQC API kept refusing {path}")  # pragma: no cover

    async def care_home_ids(self) -> AsyncIterator[str]:
        """The location id of every care home CQC lists, page by page."""
        page, pages = 1, 1
        while page <= pages:
            data = await self.get("/locations", careHome="Y", page=page, perPage=PAGE_SIZE)
            listing = LocationPage.model_validate(data)
            pages = listing.total_pages
            for location in listing.locations:
                yield location.location_id
            page += 1

    async def location(self, location_id: str) -> CqcLocation:
        return CqcLocation.model_validate(await self.get(f"/locations/{location_id}"))

    async def provider(self, provider_id: str) -> CqcProvider:
        return CqcProvider.model_validate(await self.get(f"/providers/{provider_id}"))

    async def care_homes(
        self,
        concurrency: int = 8,
        provider_names: bool = True,
        progress: Callable[[str, int, int], None] | None = None,
    ) -> list[CareHome]:
        """Every registered care home with coordinates: one request each, `concurrency` at a
        time, then (unless `provider_names` is off) one per provider for the name of who runs
        each home, which the location record does not carry."""
        gate = asyncio.Semaphore(concurrency)

        async def each(stage: str, ids: list[str], fetch: Callable[[str], Any]) -> list[Any]:
            done = 0

            async def one(item: str) -> Any:
                nonlocal done
                async with gate:
                    result = await fetch(item)
                done += 1
                if progress and (done % 250 == 0 or done == len(ids)):
                    progress(stage, done, len(ids))
                return result

            return await asyncio.gather(*(one(item) for item in ids))

        ids = [location_id async for location_id in self.care_home_ids()]
        locations = await each("care homes", ids, self.location)
        names: dict[str, str] = {}
        if provider_names:
            wanted = sorted({loc.provider_id for loc in locations if loc.provider_id})
            providers = await each("providers", wanted, self.provider)
            names = {p.provider_id: p.name for p in providers}
        homes = (care_home_from(loc, names.get(loc.provider_id, "")) for loc in locations)
        return [home for home in homes if home is not None]

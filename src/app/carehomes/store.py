"""Where the API keeps care homes and how it searches them: Neo4j (the default), or a list in
memory with `STORAGE=memory`. Both answer the same three-part search:

- `name`: every word must appear in the home's name.
- `location`: every word must appear in its address, town, county, local authority or region.
- `postcode`: the home's postcode must start with it, spaces ignored (`SA73`, `sa73 2`).

The snapshot written by `uv run task ingest` (settings.carehomes_file) is loaded when the API
starts; until one exists the bundled, made-up sample is served so the map is never empty.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

from neo4j import AsyncDriver
from pydantic import BaseModel

from app.models import CareHome, CareHomeDataset, Rating

log = logging.getLogger(__name__)
BATCH = 1000


@dataclass(frozen=True)
class Query:
    """A search, already normalised: lower-case words, and a postcode with no spaces."""

    name: tuple[str, ...] = ()
    location: tuple[str, ...] = ()
    postcode: str = ""
    ratings: tuple[Rating, ...] = ()

    @classmethod
    def of(
        cls,
        name: str = "",
        location: str = "",
        postcode: str = "",
        ratings: list[Rating] | tuple[Rating, ...] = (),
    ) -> Query:
        return cls(
            name=tuple(name.lower().split()),
            location=tuple(location.lower().split()),
            postcode=postcode_key(postcode),
            ratings=tuple(dict.fromkeys(ratings)),
        )


def postcode_key(postcode: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", postcode.upper())


def search_keys(home: CareHome) -> dict[str, str]:
    """The lower-cased text each part of a search is matched against."""
    parts = (home.address, home.town, home.county, home.local_authority, home.region)
    return {
        "name_key": home.name.lower(),
        "location_key": " ".join(part for part in parts if part).lower(),
        "postcode_key": postcode_key(home.postcode),
    }


class Snapshot(BaseModel):
    """The file `uv run task ingest` writes and the API loads."""

    dataset: CareHomeDataset
    homes: list[CareHome]


def read_snapshot(path: Path) -> Snapshot:
    return Snapshot.model_validate_json(path.read_bytes())


def write_snapshot(path: Path, snapshot: Snapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot.model_dump_json())


def sample_snapshot() -> Snapshot:
    """Made-up homes for development and demos; `dataset.source` is `sample`."""
    text = resources.files("app.carehomes").joinpath("sample.json").read_text()
    homes = [CareHome.model_validate(home) for home in json.loads(text)]
    dataset = CareHomeDataset(source="sample", name="sample.json", count=len(homes))
    return Snapshot(dataset=dataset, homes=homes)


class CareHomeStore(Protocol):
    """What the API needs from care home storage."""

    async def ping(self) -> bool: ...
    async def replace(self, snapshot: Snapshot) -> None: ...
    async def dataset(self) -> CareHomeDataset | None: ...
    async def search(
        self, query: Query, limit: int | None = None, offset: int = 0
    ) -> tuple[int, list[CareHome]]: ...
    async def get(self, location_id: str) -> CareHome | None: ...


@dataclass
class MemoryCareHomeStore:
    """Care homes in a list (STORAGE=memory, and the unit tests)."""

    homes: list[CareHome] = field(default_factory=list)
    info: CareHomeDataset | None = None
    keys: dict[str, dict[str, str]] = field(default_factory=dict)

    async def ping(self) -> bool:
        return True

    async def replace(self, snapshot: Snapshot) -> None:
        self.homes = sorted(snapshot.homes, key=lambda home: (home.name.lower(), home.location_id))
        self.keys = {home.location_id: search_keys(home) for home in self.homes}
        self.info = snapshot.dataset.model_copy(update={"count": len(self.homes)})

    async def dataset(self) -> CareHomeDataset | None:
        return self.info

    def matches(self, home: CareHome, query: Query) -> bool:
        keys = self.keys[home.location_id]
        return (
            all(word in keys["name_key"] for word in query.name)
            and all(word in keys["location_key"] for word in query.location)
            and keys["postcode_key"].startswith(query.postcode)
            and (not query.ratings or home.rating in query.ratings)
        )

    async def search(
        self, query: Query, limit: int | None = None, offset: int = 0
    ) -> tuple[int, list[CareHome]]:
        found = [home for home in self.homes if self.matches(home, query)]
        end = None if limit is None else offset + limit
        return len(found), found[offset:end]

    async def get(self, location_id: str) -> CareHome | None:
        return next((home for home in self.homes if home.location_id == location_id), None)


WHERE = """
WHERE all(word IN $name WHERE c.name_key CONTAINS word)
  AND all(word IN $location WHERE c.location_key CONTAINS word)
  AND c.postcode_key STARTS WITH $postcode
  AND (size($ratings) = 0 OR c.rating IN $ratings)
"""


class Neo4jCareHomeStore:
    """Care homes as `(:CareHome)` nodes, keyed by `location_id`, with one
    `(:CareHomeDataset)` node saying where they came from."""

    def __init__(self, driver: AsyncDriver, database: str = "neo4j") -> None:
        self.driver = driver
        self.database = database

    async def ping(self) -> bool:
        """Whether Neo4j answers."""
        try:
            await self.driver.verify_connectivity()
        except Exception:
            return False
        return True

    async def run(self, query: str, **params: Any) -> list[Any]:
        records, _, _ = await self.driver.execute_query(query, params, database_=self.database)
        return records

    async def replace(self, snapshot: Snapshot) -> None:
        dataset = snapshot.dataset.model_copy(update={"count": len(snapshot.homes)})
        stamp = dataset.loaded_at.isoformat()
        await self.run(
            "CREATE CONSTRAINT care_home_id IF NOT EXISTS "
            "FOR (c:CareHome) REQUIRE c.location_id IS UNIQUE"
        )
        rows = [
            {**home.model_dump(mode="json"), **search_keys(home), "loaded": stamp}
            for home in snapshot.homes
        ]
        for start in range(0, len(rows), BATCH):
            await self.run(
                "UNWIND $rows AS row MERGE (c:CareHome {location_id: row.location_id}) SET c = row",
                rows=rows[start : start + BATCH],
            )
        # Homes that have left the register since the last load.
        await self.run("MATCH (c:CareHome) WHERE c.loaded <> $stamp DETACH DELETE c", stamp=stamp)
        await self.run(
            "MERGE (d:CareHomeDataset {id: 'current'}) SET d += $props",
            props=dataset.model_dump(mode="json"),
        )

    async def dataset(self) -> CareHomeDataset | None:
        records = await self.run("MATCH (d:CareHomeDataset {id: 'current'}) RETURN d")
        return CareHomeDataset.model_validate(dict(records[0]["d"])) if records else None

    async def search(
        self, query: Query, limit: int | None = None, offset: int = 0
    ) -> tuple[int, list[CareHome]]:
        params = {
            "name": list(query.name),
            "location": list(query.location),
            "postcode": query.postcode,
            "ratings": list(query.ratings),
        }
        total = (await self.run(f"MATCH (c:CareHome) {WHERE} RETURN count(c) AS total", **params))[
            0
        ]["total"]
        page = "" if limit is None else "LIMIT $limit"
        records = await self.run(
            f"MATCH (c:CareHome) {WHERE} RETURN c "
            f"ORDER BY c.name_key, c.location_id SKIP $offset {page}",
            **params,
            offset=offset,
            limit=limit,
        )
        return total, [CareHome.model_validate(dict(r["c"])) for r in records]

    async def get(self, location_id: str) -> CareHome | None:
        records = await self.run(
            "MATCH (c:CareHome {location_id: $location_id}) RETURN c", location_id=location_id
        )
        return CareHome.model_validate(dict(records[0]["c"])) if records else None


async def load_startup_data(store: CareHomeStore, path: Path) -> CareHomeDataset | None:
    """Bring the store up to date when the API starts: load the snapshot at `path` if it differs
    from what the store holds, or the sample when there is no snapshot and the store is empty.
    A storage or file problem is logged, not raised, so the API still starts."""
    try:
        current = await store.dataset()
        snapshot = await asyncio.to_thread(lambda: read_snapshot(path) if path.is_file() else None)
        if snapshot is not None:
            wanted = snapshot.dataset
            if (
                current is None
                or (current.source, current.name, current.loaded_at)
                != (wanted.source, wanted.name, wanted.loaded_at)
                or current.count != len(snapshot.homes)
            ):
                await store.replace(snapshot)
                log.info("loaded %d care homes from %s", len(snapshot.homes), path)
        elif current is None:
            await store.replace(sample_snapshot())
            log.warning("no care home snapshot at %s: serving made-up sample homes", path)
        return await store.dataset()
    except Exception:
        log.exception("could not load care homes from %s", path)
        return None

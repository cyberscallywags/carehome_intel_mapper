"""Fetch care homes from the Care Quality Commission and write the snapshot the API loads.

    uv run task ingest data/2_November_2026_HSCA_Active_Locations.ods   # one you downloaded
    uv run task ingest --download     # find this month's spreadsheet on CQC's site and fetch it
    uv run task ingest --api          # read CQC's API instead; needs CQC_API_KEY

The spreadsheet is CQC's "care directory with filters", linked from
https://www.cqc.org.uk/about-us/transparency/using-cqc-data and updated monthly. The API is
updated daily and adds the five key-question ratings and the last inspection date, at one
request per home. Either way the result is `data/carehomes.json` (CAREHOMES_FILE); restart
the API to load it.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.carehomes import ATTRIBUTION
from app.carehomes.cqc_api import CqcApi, CqcApiError
from app.carehomes.directory import Report, file_date, read_directory
from app.carehomes.store import Snapshot, write_snapshot
from app.config import Settings, get_settings
from app.meta import get_meta
from app.models import RATINGS, CareHome, CareHomeDataset

DIRECTORY_LINK = re.compile(r'href="([^"]+HSCA_Active_Locations[^"]*\.ods)"', re.I)


class IngestError(RuntimeError):
    """Something the person running the command can put right; the message says how."""


def user_agent() -> str:
    meta = get_meta()
    return f"{meta.slug}/{meta.version}"


def download_directory(
    page_url: str, folder: Path, transport: httpx.BaseTransport | None = None
) -> Path:
    """Find the care directory on CQC's data page and save it under `folder`; returns the file.
    A copy already there is kept, so running this twice in a month downloads once."""
    manual = (
        f"Download 'Care directory with filters' from {page_url} in a browser, then run: "
        "uv run task ingest <the file>"
    )
    headers = {"User-Agent": user_agent()}
    with httpx.Client(
        headers=headers, timeout=120, follow_redirects=True, transport=transport
    ) as client:
        try:
            page = client.get(page_url)
            page.raise_for_status()
            if not (link := DIRECTORY_LINK.search(page.text)):
                raise IngestError(f"No link to the care directory was found on the page. {manual}")
            url = urljoin(page_url, link.group(1))
            target = folder / url.rsplit("/", 1)[-1]
            if target.is_file():
                return target
            folder.mkdir(parents=True, exist_ok=True)
            partial = target.with_suffix(".part")
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with partial.open("wb") as out:
                    for chunk in resp.iter_bytes():
                        out.write(chunk)
            partial.replace(target)
            return target
        except httpx.HTTPStatusError as exc:
            raise IngestError(
                f"CQC's site answered HTTP {exc.response.status_code} for {exc.request.url}; it "
                f"turns away some automated downloads. {manual}"
            ) from exc
        except httpx.HTTPError as exc:
            raise IngestError(f"Could not reach CQC's site ({exc}). {manual}") from exc


def from_directory(path: Path) -> tuple[Snapshot, Report]:
    if not path.is_file():
        raise IngestError(f"{path} is not a file")
    report = Report()
    try:
        homes = read_directory(path, report)
    except (ValueError, KeyError, OSError) as exc:
        raise IngestError(f"Could not read {path.name}: {exc}") from exc
    dataset = CareHomeDataset(
        source="cqc-directory", name=path.name, as_of=file_date(path.name), count=len(homes)
    )
    return Snapshot(dataset=dataset, homes=homes), report


async def from_api(
    settings: Settings,
    provider_names: bool = True,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Snapshot:
    if settings.cqc_api_key is None:
        raise IngestError(
            "Set CQC_API_KEY to your subscription key. Register and request one at "
            "https://api-portal.service.cqc.org.uk (it is on your profile page afterwards)."
        )

    def progress(stage: str, done: int, total: int) -> None:
        print(f"  {stage}: {done:,} of {total:,}", flush=True)

    try:
        async with CqcApi(
            settings.cqc_api_url,
            settings.cqc_api_key.get_secret_value(),
            settings.cqc_partner_code,
            transport=transport,
        ) as api:
            homes = await api.care_homes(provider_names=provider_names, progress=progress)
    except CqcApiError as exc:
        raise IngestError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise IngestError(f"The CQC API request failed: {exc}") from exc
    dataset = CareHomeDataset(source="cqc-api", name=settings.cqc_api_url, count=len(homes))
    return Snapshot(dataset=dataset, homes=homes)


def summary(homes: list[CareHome]) -> str:
    counts = {rating: sum(home.rating == rating for home in homes) for rating in RATINGS}
    return ", ".join(f"{rating} {count:,}" for rating, count in counts.items())


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="task ingest", description="Write the care home snapshot from CQC's public data."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("file", nargs="?", type=Path, help="CQC's care directory (.ods or .csv)")
    source.add_argument("--download", action="store_true", help="fetch the directory from CQC")
    source.add_argument("--api", action="store_true", help="read CQC's API (needs CQC_API_KEY)")
    parser.add_argument(
        "--no-provider-names",
        action="store_true",
        help="with --api: skip the extra request per provider for its name",
    )
    parser.add_argument("--out", type=Path, help="snapshot to write (default: CAREHOMES_FILE)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    settings = get_settings()
    out: Path = args.out or settings.carehomes_file
    try:
        if args.api:
            print(f"Reading care homes from {settings.cqc_api_url} ...")
            snapshot = asyncio.run(from_api(settings, provider_names=not args.no_provider_names))
        else:
            path = args.file or download_directory(settings.cqc_data_page, out.parent)
            print(f"Reading {path} ...")
            snapshot, report = from_directory(path)
            print(f"  {report.rows:,} locations, {report.care_homes:,} of them care homes")
            for reason, count in report.skipped.items():
                print(f"  left out {count:,}: {reason}")
        if not snapshot.homes:
            raise IngestError("No care homes were found, so nothing was written.")
    except IngestError as exc:
        print(f"ingest: {exc}", file=sys.stderr)
        return 1
    write_snapshot(out, snapshot)
    print(f"Wrote {len(snapshot.homes):,} care homes to {out}")
    print(f"  {summary(snapshot.homes)}")
    print(f"  {ATTRIBUTION}")
    print("Restart the API to load them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

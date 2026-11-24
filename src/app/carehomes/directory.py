"""Turn CQC's "care directory with filters" spreadsheet (the monthly
`..._HSCA_Active_Locations.ods` on https://www.cqc.org.uk/about-us/transparency/using-cqc-data)
into care homes. It lists every active location with its coordinates, whether it is a care home,
its bed count and its latest overall rating. The same sheet saved as CSV is read too.

Columns are found by their heading, not their position, so CQC adding or moving a column does
not break the import; a missing required heading stops it with the headings that were found.
"""

import csv
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from app.carehomes.cqc_models import to_date, to_rating, to_website
from app.carehomes.ods import read_sheets
from app.models import CareHome

# Our field -> the spreadsheet's heading, compared with case and punctuation ignored.
COLUMNS = {
    "location_id": "Location ID",
    "name": "Location Name",
    "care_home": "Care home?",
    "beds": "Care homes beds",
    "rating": "Location Latest Overall Rating",
    "rating_published": "Publication Date",
    "region": "Location Region",
    "local_authority": "Location Local Authority",
    "street": "Location Street Address",
    "line2": "Location Address Line 2",
    "town": "Location City",
    "county": "Location County",
    "postcode": "Location Postal Code",
    "latitude": "Location Latitude",
    "longitude": "Location Longitude",
    "phone": "Location Telephone Number",
    "website": "Location Web Address",
    "provider_id": "Provider ID",
    "provider_name": "Provider Name",
    "registered": "Location HSCA start date",
    "inspection_category": "Location Primary Inspection Category",
    "constituency": "Location Parliamentary Constituency",
    "brand_name": "Brand Name",
    "also_known_as": "Location Also Known As",
}
REQUIRED = ("location_id", "name", "care_home", "postcode", "latitude", "longitude", "rating")
# Yes/no columns, one per value: `Service type - Care home service with nursing` and so on.
FLAG_COLUMNS = {
    "service_types": "service type ",
    "specialisms": "service user band ",
    "regulated_activities": "regulated activity ",
}


def key(heading: str) -> str:
    """A heading with case, punctuation and spacing ignored: `Care home?` -> `care home`."""
    return re.sub(r"[^a-z0-9]+", " ", heading.lower()).strip()


def to_int(text: str | None) -> int | None:
    try:
        value = int(float((text or "").strip()))
    except ValueError:
        return None
    return value if value >= 0 else None


def file_date(name: str) -> date | None:
    """The publication date in a CQC file name such as `2_November_2026_HSCA_...ods`."""
    if match := re.search(r"(\d{1,2})[_ ]([A-Za-z]+)[_ ](\d{4})", name):
        return to_date(" ".join(match.groups()))
    return None


@dataclass
class Report:
    """What an import read, for the command's summary."""

    rows: int = 0
    care_homes: int = 0
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def _rows(path: Path) -> Iterator[list[str]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            yield from csv.reader(handle)
    else:
        for _sheet, row in read_sheets(path):
            yield row


def parse_rows(rows: Iterable[list[str]], report: Report | None = None) -> Iterator[CareHome]:
    """Care homes from the directory's rows. Notes above the heading row are skipped; rows that
    are not care homes, or have no usable coordinates, are counted in `report`. The directory
    has the overall rating only: the key-question ratings come from the API."""
    report = report if report is not None else Report()
    index: dict[str, int] | None = None
    flags: dict[str, dict[int, str]] = {}
    wanted = key(COLUMNS["location_id"])
    seen: set[str] = set()
    for row in rows:
        if index is None:
            headings = [key(cell) for cell in row]
            if wanted not in headings:
                continue
            index = {
                name: headings.index(key(title))
                for name, title in COLUMNS.items()
                if key(title) in headings
            }
            if missing := [COLUMNS[name] for name in REQUIRED if name not in index]:
                raise ValueError(
                    f"The spreadsheet has no column named {', '.join(missing)}. It should be "
                    "CQC's 'care directory with filters' (HSCA_Active_Locations). "
                    f"Columns found: {', '.join(c for c in row if c)}"
                )
            flags = {
                name: {
                    i: row[i].split("-", 1)[-1].strip()
                    for i, heading in enumerate(headings)
                    if heading.startswith(prefix)
                }
                for name, prefix in FLAG_COLUMNS.items()
            }
            continue

        def cell(name: str, row: list[str] = row, index: dict[str, int] = index) -> str:
            i = index.get(name)
            return row[i].strip() if i is not None and i < len(row) else ""

        def ticked(
            name: str, row: list[str] = row, flags: dict[str, dict[int, str]] = flags
        ) -> list[str]:
            return [
                title
                for i, title in flags[name].items()
                if i < len(row) and row[i].strip().upper() in {"Y", "YES"}
            ]

        report.rows += 1
        if cell("care_home").upper() not in {"Y", "YES"}:
            continue
        location_id = cell("location_id")
        if not location_id or location_id in seen:
            report.skip("no location id, or listed twice")
            continue
        try:
            home = CareHome(
                location_id=location_id,
                name=cell("name"),
                address=", ".join(part for part in (cell("street"), cell("line2")) if part),
                town=cell("town"),
                county=cell("county"),
                postcode=cell("postcode").upper(),
                local_authority=cell("local_authority"),
                region=cell("region"),
                latitude=float(cell("latitude")),
                longitude=float(cell("longitude")),
                rating=to_rating(cell("rating")),
                rating_published=to_date(cell("rating_published")),
                beds=to_int(cell("beds")),
                service_types=ticked("service_types"),
                specialisms=ticked("specialisms"),
                regulated_activities=ticked("regulated_activities"),
                registered=to_date(cell("registered")),
                inspection_category=cell("inspection_category"),
                constituency=cell("constituency"),
                brand_name="" if cell("brand_name") in {"-", "None"} else cell("brand_name"),
                also_known_as=cell("also_known_as"),
                phone=cell("phone"),
                website=to_website(cell("website")),
                provider_id=cell("provider_id"),
                provider_name=cell("provider_name"),
            )
        except ValueError, ValidationError:
            report.skip("no usable latitude and longitude")
            continue
        seen.add(location_id)
        report.care_homes += 1
        yield home
    if index is None:
        raise ValueError(
            f"No heading row with a '{COLUMNS['location_id']}' column was found. The file should "
            "be CQC's 'care directory with filters' (HSCA_Active_Locations)."
        )


def read_directory(path: Path, report: Report | None = None) -> list[CareHome]:
    """Every care home in the directory file at `path` (.ods, or the same sheet as .csv)."""
    return list(parse_rows(_rows(path), report))

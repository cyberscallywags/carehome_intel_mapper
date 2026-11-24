"""Reading CQC's care directory spreadsheet (app.carehomes.ods, app.carehomes.directory)."""

import zipfile
from datetime import date

import pytest

from app.carehomes import directory
from app.carehomes.ods import read_sheets

HEADINGS = [
    "Location ID",
    "Location HSCA start date",
    "Care home?",
    "Location Name",
    "Location Telephone Number",
    "Location Web Address",
    "Care homes beds",
    "Location Latest Overall Rating",
    "Publication Date",
    "Location Region",
    "Location Local Authority",
    "Location Street Address",
    "Location Address Line 2",
    "Location City",
    "Location County",
    "Location Postal Code",
    "Location Latitude",
    "Location Longitude",
    "Provider ID",
    "Provider Name",
    "Service type - Care home service with nursing",
    "Service type - Care home service without nursing",
    "Service user band - Dementia",
    "Service user band - Younger Adults",
    "Regulated activity - Accommodation for persons who require nursing or personal care",
    "Location Primary Inspection Category",
    "Location Parliamentary Constituency",
    "Brand Name",
]


def directory_row(**changes: str) -> list[str]:
    row = {
        "Location ID": "1-101",
        "Location HSCA start date": "2011-01-17",
        "Care home?": "Y",
        "Location Name": "Ty Example",
        "Location Telephone Number": "01234567890",
        "Location Web Address": "www.example.org",
        "Care homes beds": "42",
        "Location Latest Overall Rating": "Requires improvement",
        "Publication Date": "2025-06-20",
        "Location Region": "South West",
        "Location Local Authority": "Bristol, City of",
        "Location Street Address": "1 Example Street",
        "Location Address Line 2": "Redland",
        "Location City": "Bristol",
        "Location County": "",
        "Location Postal Code": "bs1 9zz",
        "Location Latitude": "51.454513",
        "Location Longitude": "-2.587910",
        "Provider ID": "1-9",
        "Provider Name": "Example Care Ltd",
        "Service type - Care home service with nursing": "Y",
        "Service type - Care home service without nursing": "",
        "Service user band - Dementia": "Y",
        "Service user band - Younger Adults": "",
        "Regulated activity - Accommodation for persons who require nursing or personal care": "Y",
        "Location Primary Inspection Category": "Residential social care",
        "Location Parliamentary Constituency": "Bristol Central",
        "Brand Name": "-",
    } | changes
    return [row[heading] for heading in HEADINGS]


def cell(value: str, kind: str = "string", repeat: int = 1) -> str:
    stored = {"float": f' office:value="{value}"', "date": f' office:date-value="{value}"'}
    repeated = f' table:number-columns-repeated="{repeat}"' if repeat > 1 else ""
    shown = "shown differently" if kind != "string" else value
    body = f"<text:p>{shown}</text:p>" if value else ""
    return (
        f'<table:table-cell office:value-type="{kind}"{stored.get(kind, "")}{repeated}>'
        f"{body}</table:table-cell>"
    )


def write_ods(path, sheets: dict[str, list[str]]) -> None:
    """A minimal .ods: `sheets` maps a sheet name to its rows, each a string of cell XML."""
    tables = "".join(
        f'<table:table table:name="{name}">'
        + "".join(f"<table:table-row>{row}</table:table-row>" for row in rows)
        + '<table:table-row table:number-rows-repeated="1048000"><table:table-cell '
        'table:number-columns-repeated="16384"/></table:table-row></table:table>'
        for name, rows in sheets.items()
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?><office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        f"<office:body><office:spreadsheet>{tables}</office:spreadsheet></office:body>"
        "</office:document-content>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        archive.writestr("content.xml", content)


def test_ods_reads_stored_values_repeats_and_spaces(tmp_path):
    path = tmp_path / "book.ods"
    spaced = (
        '<table:table-cell office:value-type="string"><text:p>two<text:s text:c="2"/>'
        "spaces</text:p></table:table-cell>"
    )
    write_ods(
        path,
        {
            "Notes": [cell("About this file")],
            "Data": [
                cell("a") + cell("", repeat=2) + cell("d"),
                cell("51.454513", "float") + cell("2025-06-20", "date") + spaced,
            ],
        },
    )
    assert list(read_sheets(path)) == [
        ("Notes", ["About this file"]),
        ("Data", ["a", "", "", "d"]),
        ("Data", ["51.454513", "2025-06-20", "two  spaces"]),
    ]


def test_directory_keeps_care_homes_and_maps_their_columns(tmp_path):
    path = tmp_path / "2_November_2026_HSCA_Active_Locations.ods"
    rows = [
        directory_row(),
        directory_row(**{"Location ID": "1-102", "Care home?": "N"}),
        directory_row(**{"Location ID": "1-103", "Location Latitude": ""}),
        directory_row(**{"Location ID": "1-104", "Location Latest Overall Rating": "-"}),
        directory_row(),  # listed twice
    ]
    write_ods(
        path,
        {
            "README": [cell("Care directory with filters")],
            "HSCA_Active_Locations": [
                "".join(cell(v) for v in row) for row in [["Published by CQC"], HEADINGS, *rows]
            ],
        },
    )
    report = directory.Report()
    homes = directory.read_directory(path, report)
    assert [h.location_id for h in homes] == ["1-101", "1-104"]
    first = homes[0]
    assert first.model_dump(exclude_defaults=True) == {
        "location_id": "1-101",
        "name": "Ty Example",
        "address": "1 Example Street, Redland",
        "town": "Bristol",
        "postcode": "BS1 9ZZ",
        "local_authority": "Bristol, City of",
        "region": "South West",
        "constituency": "Bristol Central",
        "latitude": 51.454513,
        "longitude": -2.58791,
        "rating": "Requires improvement",
        "rating_published": date(2025, 6, 20),
        "registered": date(2011, 1, 17),
        "beds": 42,
        "inspection_category": "Residential social care",
        "service_types": ["Care home service with nursing"],
        "specialisms": ["Dementia"],
        "regulated_activities": ["Accommodation for persons who require nursing or personal care"],
        "phone": "01234567890",
        "website": "https://www.example.org",
        "provider_id": "1-9",
        "provider_name": "Example Care Ltd",
    }
    assert homes[1].rating == "Not rated"
    assert (report.rows, report.care_homes) == (5, 2)
    assert report.skipped == {
        "no usable latitude and longitude": 1,
        "no location id, or listed twice": 1,
    }
    assert directory.file_date(path.name) == date(2026, 11, 2)


def test_directory_reads_the_same_sheet_saved_as_csv(tmp_path):
    path = tmp_path / "directory.csv"
    lines = [HEADINGS, directory_row()]
    path.write_text("\n".join(",".join(f'"{v}"' for v in line) for line in lines))
    assert [h.name for h in directory.read_directory(path)] == ["Ty Example"]


def test_directory_says_which_columns_are_missing():
    with pytest.raises(ValueError, match="no column named Location Latitude, Location Longitude"):
        list(
            directory.parse_rows(
                [
                    [
                        "Location ID",
                        "Location Name",
                        "Care home?",
                        "Location Postal Code",
                        "Location Latest Overall Rating",
                    ]
                ]
            )
        )
    with pytest.raises(ValueError, match="No heading row"):
        list(directory.parse_rows([["Name", "Postcode"]]))


@pytest.mark.parametrize(
    ("text", "rating"),
    [
        ("Outstanding", "Outstanding"),
        ("requires improvement", "Requires improvement"),
        ("Requires Improvement", "Requires improvement"),
        ("Insufficient evidence to rate", "Not rated"),
        ("", "Not rated"),
        (None, "Not rated"),
    ],
)
def test_rating_bands(text, rating):
    assert directory.to_rating(text) == rating


@pytest.mark.parametrize(
    ("text", "link"),
    [
        ("www.example.org", "https://www.example.org"),
        ("http://example.org/home", "http://example.org/home"),
        ("javascript:alert(1)", ""),
        ("not a link", ""),
        ("", ""),
    ],
)
def test_website_is_only_ever_a_web_link(text, link):
    assert directory.to_website(text) == link

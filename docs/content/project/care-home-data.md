# Care home data

Everything shown comes from the Care Quality Commission's public data, described on CQC's
[Using CQC data](https://www.cqc.org.uk/about-us/transparency/using-cqc-data) page and
published under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
The app must keep saying so: the attribution is on the map, in both search menus and in the
about page.

## Loading it

`uv run task ingest` reads CQC's data and writes a snapshot, `data/carehomes.json`
(`CAREHOMES_FILE`). The API loads the snapshot when it starts, into Neo4j or into memory with
`STORAGE=memory`; restart the API after an ingest. With no snapshot it serves made-up sample
homes, marked as such.

```bash
uv run task ingest data/2_November_2026_HSCA_Active_Locations.ods   # a spreadsheet you downloaded
uv run task ingest --download                                       # fetch this month's from CQC
CQC_API_KEY=... uv run task ingest --api                            # CQC's API instead
```

In Docker the `api` service reads `./data` (mounted at `/data`), so run the ingest on the
host and then `docker compose restart api`.

### From the spreadsheet

CQC publishes the **care directory with filters** each month
(`..._HSCA_Active_Locations.ods`, about 25 MB). It lists every active location with its
coordinates, whether it is a care home, its beds and its latest overall rating. The ingest
keeps the rows where *Care home?* is `Y` and that have a latitude and longitude, and reports
how many it left out.

`--download` finds the file's link on CQC's page and saves it beside the snapshot. CQC's site
turns away some automated downloads (HTTP 403); when it does, the command says so: download
the file in a browser and pass its path instead.

Columns are matched by heading, so a moved or added column does not matter. If CQC renames
one of the headings the import needs, it stops and lists the headings it found; the names are
in `COLUMNS` in `src/app/carehomes/directory.py`.

### From the API

CQC's syndication API is updated daily and has more for each home: the rating for each of the
five key questions (Safe, Effective, Caring, Responsive, Well-led) and the last inspection
date.

1. Register at the [CQC API portal](https://api-portal.service.cqc.org.uk) and activate the
   account from the email it sends.
2. Request a subscription key; it is then on your profile page.
3. Set it as `CQC_API_KEY`. It is sent on every request as the
   `Ocp-Apim-Subscription-Key` header; without a valid key the API answers 401.

`--api` lists the care homes (`GET /locations?careHome=Y`), then reads each one
(`GET /locations/{id}`) and each provider's name (`GET /providers/{id}`), eight requests at a
time, waiting when the API asks it to slow down. That is one request per home, so allow
several minutes; `--no-provider-names` skips the provider requests. Set `CQC_PARTNER_CODE` if
CQC has given you one.

| Setting | For |
|---|---|
| `CAREHOMES_FILE` | Where the snapshot is written and read (`data/carehomes.json`). |
| `CQC_API_KEY` | The subscription key. Needed by `--api` and by `GET /carehomes/{id}/cqc`. |
| `CQC_API_URL` | The API's base address (`https://api.service.cqc.org.uk/public/v1`). |
| `CQC_PARTNER_CODE` | Optional `partnerCode` added to each request. |
| `CQC_DATA_PAGE` | The page `--download` reads to find the spreadsheet. |

## The models

`src/app/carehomes/cqc_models.py` holds CQC's own shapes, written from the JSON schemas CQC
publishes with its API guide: `CqcLocation` and `CqcProvider`, with their ratings (current and
historic, overall, per service and per key question), reports, regulated activities,
inspection categories, specialisms and single-assessment-framework assessments. They are
forgiving on purpose: nothing is required, unknown fields are ignored and an unreadable date
becomes empty, because the data is someone else's and changes without notice.

`CareHome` in `src/app/models.py` is what the app keeps and serves, built from a location by
`care_home_from`:

| `CareHome` | From the API | From the spreadsheet |
|---|---|---|
| `rating`, `rating_published` | `currentRatings.overall` | *Location Latest Overall Rating*, *Publication Date* |
| `rating_safe` … `rating_well_led` | `currentRatings.overall.keyQuestionRatings` | not in the file |
| `last_inspected` | `lastInspection.date` | not in the file |
| `latitude`, `longitude` | `onspdLatitude`, `onspdLongitude` | *Location Latitude*, *Location Longitude* |
| `beds` | `numberOfBeds` | *Care homes beds* |
| `service_types` | `gacServiceTypes` | the *Service type - …* columns |
| `specialisms` | `specialisms` | the *Service user band - …* columns |
| `provider_name` | the provider's `name` | *Provider Name* |

Every rating is one of five bands: Outstanding, Good, Requires improvement, Inadequate, or
Not rated. Not rated covers every home without a published rating, whatever CQC's reason.

CQC's records name registered managers and nominated individuals. The app does not store or
show them; they appear only in the live record below, as CQC publishes them.

## The API

| Endpoint | Returns |
|---|---|
| `GET /carehomes?name=&location=&postcode=&rating=` | Matching homes in name order, the total, and where the data came from. |
| `GET /carehomes/map?…&focus=` | The map for the same search, as an HTML page for a frame. |
| `GET /carehomes/{location_id}` | One home. |
| `GET /carehomes/{location_id}/cqc` | CQC's full, current record, read from its API as you ask. Needs `CQC_API_KEY` on the server. |

The generated [HTTP API](../reference/http-api.md) and [Data models](../reference/models.md)
pages have every parameter and field.

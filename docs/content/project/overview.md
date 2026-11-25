# Project overview

Carehome Intel helps people find care homes in England and see how the regulator, the Care
Quality Commission (CQC), rates them. It puts CQC's public data on a map that works in a
browser and on a phone.

## What it does today

- **A map of care homes.** Each home is a marker in the colour of its latest overall CQC
  rating, with the rating's initial on it so colour is never the only cue. Hovering names the
  home and its rating; selecting it opens its address, beds, type of care, who runs it, the
  rating for each of CQC's five key questions when known, and a link to its inspection
  reports on CQC's website.
- **A search side menu**, on the web UI's Map page and the mobile app's Map screen: by name,
  by location (town, county, council area or region) or by the start of a postcode, and by
  rating. On a phone the menu slides over the map; on a wide screen it stays beside it.
- **CQC's data, two ways**: its monthly spreadsheet, or its API. See
  [Care home data](care-home-data.md).

## Who it is for

People choosing a care home for themselves or a relative, and anyone who wants the
regulator's view of the homes in an area without reading a spreadsheet.

## The domain

| Thing | Where | Notes |
|---|---|---|
| `CareHome` | `src/app/models.py` | What the API serves: one registered care home with its ratings. Read-only; it comes from CQC. |
| `CqcLocation`, `CqcProvider` | `src/app/carehomes/cqc_models.py` | CQC's own records, as its API returns them. |
| Search, storage | `src/app/carehomes/store.py` | `(:CareHome)` nodes in Neo4j, or a list in memory with `STORAGE=memory`. |
| The map | `src/app/carehomes/mapview.py` | A Folium page served by the API at `GET /carehomes/map`. |

The template's sample `Item` has been removed: care homes are the only domain, and
`POST /ask` answers questions about them.

## Decisions

- **The map is one HTML page made by the API** (Folium), and both frontends show it in a
  frame. One map to maintain, identical on web and mobile. Markers are drawn in the browser
  from one compact row per home, so the whole register (about fifteen thousand homes) is a
  page of a few megabytes and opens in a second or two.
- **The web UI's Map page is plain HTML, not FastUI components.** FastUI has no side menu and
  cannot hold a frame beside a form. The search is an ordinary form whose fields are the
  page's address, so a search can be bookmarked and shared, and it works without scripts.
- **The mobile search menu is not an `ion-menu`.** Ionic turns every menu inside the app's
  split pane into a fixed pane on wide screens, where it can no longer be opened, so the menu
  is a panel of the page's own.
- **Care homes are loaded from a snapshot file**, written by `uv run task ingest`, when the
  API starts. Reading CQC's data and serving it are kept apart, so the site never depends on
  CQC's site being up.
- **Sample data is labelled.** Until a snapshot exists the API serves made-up homes, and the
  map and the menus say so.

## Not done yet

- Homes are found by the text of their address and postcode, not by distance from a place.
- Only the latest ratings are kept; CQC's rating history and report text are not stored
  (`GET /carehomes/{id}/cqc` reads them live from CQC).
- Providers are a name on each home, not yet nodes of their own in the graph.

The template's own documentation is the [Template handbook](../handbook/index.md).

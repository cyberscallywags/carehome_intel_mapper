"""Care homes: records read from the Care Quality Commission's public data, a searchable
store for them, and the map both frontends show.

- `ods`, `directory`: read CQC's monthly "care directory with filters" spreadsheet.
- `cqc_api`: read the same records from CQC's syndication API (needs a subscription key).
- `ingest`: the command behind `uv run task ingest`, which writes the snapshot the API loads.
- `store`: where the API keeps them (Neo4j, or memory with `STORAGE=memory`) and how it searches.
- `mapview`: the Folium map. `routes`: the API's `/carehomes` endpoints.

CQC's data is published under the Open Government Licence v3.0."""

from app.models import Rating

# One colour and one letter per rating, shared by the map's markers and the web UI's result
# list. The colours stay distinct for colour-blind readers and carry white text (WCAG AA); the
# letter means colour is never the only cue.
COLOURS: dict[Rating, str] = {
    "Outstanding": "#1d4ed8",
    "Good": "#15803d",
    "Requires improvement": "#b45309",
    "Inadequate": "#b91c1c",
    "Not rated": "#4b5563",
}
INITIALS: dict[Rating, str] = {
    "Outstanding": "O",
    "Good": "G",
    "Requires improvement": "R",
    "Inadequate": "I",
    "Not rated": "–",
}

ATTRIBUTION = (
    "Contains Care Quality Commission data, licensed under the Open Government Licence v3.0."
)

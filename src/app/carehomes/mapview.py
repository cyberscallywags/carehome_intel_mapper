"""The care home map: a Folium (Leaflet) page the web UI and the mobile app both show in a
frame. Every home is a marker in its rating's colour, carrying the rating's initial so colour is
never the only cue; hovering names the home and its rating, and a click opens its details.

Markers are built in the browser from one compact row per home (FastMarkerCluster), so the whole
register, about fifteen thousand homes, is a page of a couple of megabytes rather than tens.
"""

from collections import Counter
from html import escape

import folium
from branca.element import Element, MacroElement
from folium.plugins import FastMarkerCluster
from jinja2 import Template

from app.carehomes import ATTRIBUTION, COLOURS, INITIALS
from app.models import KEY_QUESTIONS, RATINGS, CareHome, CareHomeDataset

ENGLAND = (52.8, -1.6)
TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_CREDIT = (
    '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" '
    'rel="noopener">OpenStreetMap</a> contributors · Care home data: '
    '<a href="https://www.cqc.org.uk/about-us/transparency/using-cqc-data" target="_blank" '
    'rel="noopener">CQC</a>, OGL v3.0'
)

STYLE = """<style>
.ch-pin { display: flex; align-items: center; justify-content: center; width: 26px; height: 26px;
  border-radius: 50%; border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,.45);
  color: #fff; font: 700 13px/1 system-ui, sans-serif; }
.ch-pin.ch-focus { width: 34px; height: 34px; font-size: 16px; outline: 3px solid #111; }
.ch-popup { font: 14px/1.4 system-ui, sans-serif; min-width: 220px; }
.ch-popup h3 { font-size: 16px; margin: 0 0 6px; }
.ch-popup p { margin: 4px 0; }
.ch-popup ul { list-style: none; margin: 4px 0; padding: 0; }
.ch-popup li { display: flex; justify-content: space-between; gap: 12px; }
.ch-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; color: #fff;
  font-weight: 600; }
.ch-legend, .ch-note { position: fixed; z-index: 1000; background: #fff; color: #111;
  font: 13px/1.4 system-ui, sans-serif; border-radius: 6px; box-shadow: 0 1px 5px rgba(0,0,0,.4); }
.ch-legend { left: 10px; bottom: 48px; padding: 8px 10px; }
.ch-legend summary { font-weight: 600; cursor: pointer; }
.ch-legend ul { list-style: none; margin: 0; padding: 0; }
.ch-legend li { display: flex; align-items: center; gap: 6px; margin: 2px 0; }
.ch-legend .ch-pin { width: 18px; height: 18px; font-size: 10px; border-width: 1px;
  box-shadow: none; }
.ch-note { top: 10px; left: 50%; transform: translateX(-50%); padding: 6px 12px;
  max-width: calc(100% - 110px); text-align: center; }
.ch-note.ch-sample { background: #fef3c7; border: 1px solid #b45309; }
@media (max-width: 480px) { .ch-legend { font-size: 12px; padding: 6px 8px; } }
</style>"""

# Runs in the browser once per row; `row` is one list from `rows()` below. Every value is
# inserted as text (esc), never as markup.
CALLBACK = """function (row) {
  var colours = %(colours)s, labels = %(labels)s, initials = %(initials)s;
  var questions = %(questions)s;
  var esc = function (value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  };
  var rating = row[2], colour = colours[rating], label = labels[rating];
  var pin = L.divIcon({
    className: '', iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -12],
    html: '<span class="ch-pin" style="background:' + colour + '">' + initials[rating] + '</span>'
  });
  var marker = L.marker(new L.LatLng(row[0], row[1]), {icon: pin});
  marker.on('add', function () {  // a name for screen readers; the pin itself is one letter
    var el = marker.getElement();
    if (el) { el.setAttribute('aria-label', row[3] + ', ' + label); }
  });
  marker.bindTooltip(esc(row[3]) + ' · ' + label, {direction: 'top', offset: [0, -12]});
  marker.bindPopup(function () {
    var html = '<div class="ch-popup"><h3>' + esc(row[3]) + '</h3>' +
      '<p><span class="ch-badge" style="background:' + colour + '">' + label + '</span></p>';
    if (row[8]) { html += '<p>Report published ' + esc(row[8]) + '</p>'; }
    if (row[14]) {
      html += '<ul>';
      row[14].forEach(function (answer, i) {
        if (answer >= 0) {
          html += '<li><span>' + questions[i] + '</span><strong>' + labels[answer] +
            '</strong></li>';
        }
      });
      html += '</ul>';
    }
    html += '<p>' + esc(row[4]) + '<br>' + esc(row[5]) + '</p>';
    if (row[6] != null) { html += '<p>Beds: ' + esc(row[6]) + '</p>'; }
    if (row[7]) { html += '<p>' + esc(row[7]) + '</p>'; }
    if (row[12]) { html += '<p>Run by ' + esc(row[12]) + '</p>'; }
    if (row[10]) {
      html += '<p>Phone: <a href="tel:' + esc(String(row[10]).replace(/[^0-9+]/g, '')) + '">' +
        esc(row[10]) + '</a></p>';
    }
    if (/^https?:\\/\\//i.test(row[11] || '')) {
      html += '<p><a href="' + esc(row[11]) + '" target="_blank" rel="noopener noreferrer">' +
        'Website</a></p>';
    }
    if (row[13]) {
      html += '<p><a href="https://www.cqc.org.uk/location/' + encodeURIComponent(row[9]) +
        '" target="_blank" rel="noopener noreferrer">Inspection reports on the CQC website</a></p>';
    }
    return html + '</div>';
  }, {maxWidth: 300, autoPanPaddingTopLeft: [10, %(clear_top)d]});
  return marker;
}"""


def js_callback(clear_top: int = 10) -> str:
    """The marker-building function; `clear_top` keeps an opened popup below a note that many
    pixels tall at the top of the map."""
    quote = lambda items: "[" + ", ".join(f"'{item}'" for item in items) + "]"  # noqa: E731
    return CALLBACK % {
        "colours": quote(COLOURS[r] for r in RATINGS),
        "labels": quote(RATINGS),
        "initials": quote(INITIALS[r] for r in RATINGS),
        "questions": quote(KEY_QUESTIONS),
        "clear_top": clear_top,
    }


class FocusMarker(MacroElement):
    """One home drawn outside the clusters, with its details already open."""

    _template = Template(
        "{% macro script(this, kwargs) %}"
        "(function () { var marker = ({{ this.callback }})({{ this.row|tojson }});"
        " marker.addTo({{ this._parent.get_name() }}); marker.openPopup(); })();"
        "{% endmacro %}"
    )

    def __init__(self, callback: str, row: list) -> None:
        super().__init__()
        self._name = "FocusMarker"
        self.callback = callback
        self.row = row


def row(home: CareHome, real: bool) -> list:
    """One home as the list the browser callback reads, by position."""
    place = ", ".join(part for part in (home.address, home.town, home.county) if part)
    published = home.rating_published.strftime("%-d %B %Y") if home.rating_published else ""
    answers = home.key_question_ratings
    return [
        round(home.latitude, 6),
        round(home.longitude, 6),
        RATINGS.index(home.rating),
        home.name,
        place,
        home.postcode,
        home.beds,
        ", ".join(home.service_types),
        published,
        home.location_id,
        home.phone,
        home.website,
        home.provider_name,
        real,  # link to the CQC website only for real records
        [RATINGS.index(answers[q]) if q in answers else -1 for q in KEY_QUESTIONS]
        if answers
        else None,
    ]


def legend(homes: list[CareHome]) -> str:
    counts = Counter(home.rating for home in homes)
    items = "".join(
        f'<li><span class="ch-pin" style="background:{COLOURS[rating]}" aria-hidden="true">'
        f"{INITIALS[rating]}</span>{escape(rating)} ({counts[rating]:,})</li>"
        for rating in RATINGS
    )
    # Open beside the map on a wide screen; on a phone it starts as one line the reader can open.
    return (
        '<details class="ch-legend" open><summary>Latest CQC rating</summary>'
        f"<ul>{items}</ul></details>"
        "<script>if (window.innerWidth < 500) {"
        " document.querySelector('.ch-legend').removeAttribute('open'); }</script>"
    )


def note(homes: list[CareHome], dataset: CareHomeDataset | None) -> str:
    if dataset is not None and dataset.source == "sample":
        return (
            '<div class="ch-note ch-sample" role="status">Sample data: these homes are made up. '
            "Load CQC's data with <code>uv run task ingest</code>.</div>"
        )
    if not homes:
        return '<div class="ch-note" role="status">No care homes match this search.</div>'
    return ""


def render_map(
    homes: list[CareHome],
    dataset: CareHomeDataset | None = None,
    focus: CareHome | None = None,
) -> str:
    """The whole map page as HTML. `focus` is one home to centre on with its details open."""
    real = dataset is None or dataset.source != "sample"
    area = folium.Map(location=ENGLAND, zoom_start=6, tiles=None)
    folium.TileLayer(TILES, attr=TILE_CREDIT, name="OpenStreetMap", max_zoom=19).add_to(area)
    banner = note(homes, dataset)
    callback = js_callback(clear_top=90 if banner else 10)
    others = [home for home in homes if focus is None or home.location_id != focus.location_id]
    if others:
        FastMarkerCluster(
            [row(home, real) for home in others],
            callback=callback,
            name="Care homes",
            options={"maxClusterRadius": 50, "disableClusteringAtZoom": 15},
        ).add_to(area)
    shown = homes if focus is None else [focus]
    if shown:
        lats = [home.latitude for home in shown]
        lons = [home.longitude for home in shown]
        area.fit_bounds(
            [[min(lats), min(lons)], [max(lats), max(lons)]],
            max_zoom=15,
            padding_top_left=(30, 90 if banner else 30),
            padding_bottom_right=(30, 60),
        )
    if focus is not None:  # after the view is set, so opening its details pans them into view
        FocusMarker(callback, row(focus, real)).add_to(area)
    root = area.get_root()
    root.title = "Care home map"
    root.header.add_child(Element(STYLE))
    root.html.add_child(Element(legend(homes) + banner))
    root.html.add_child(Element(f"<!-- {escape(ATTRIBUTION)} -->"))
    return root.render()

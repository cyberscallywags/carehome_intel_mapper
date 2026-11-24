"""The web UI's map page (`/map`): a search menu beside the care home map. Plain server-rendered
HTML rather than FastUI components, because FastUI has no side menu and the map is a frame.

The search is an ordinary GET form, so a search is a link that can be shared and the page works
without scripts; the script only opens and closes the menu on narrow screens, where it slides
over the map. On wide screens the menu stays open beside it.
"""

from html import escape
from urllib.parse import urlencode

from app.carehomes import ATTRIBUTION, COLOURS, INITIALS
from app.models import RATINGS, CareHomeDataset, CareHomePage, Site

SEARCH_FIELDS = ("name", "location", "postcode", "rating")
LISTED = 50  # results shown in the menu; the map shows every match

CSS = """
*, *::before, *::after { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { display: flex; flex-direction: column; font-family: var(--font); color: #1f2933;
  background: #fff; }
a { color: var(--primary); }
:focus-visible { outline: 3px solid var(--tertiary); outline-offset: 2px; }
.bar { display: flex; align-items: center; gap: 1rem; padding: .5rem 1rem; min-height: 3.25rem;
  background: var(--primary); color: #fff; }
.bar a { color: #fff; text-decoration: none; }
.bar .brand { font-weight: 600; font-size: 1.15rem; margin-right: auto; }
.bar nav { display: flex; gap: 1rem; }
.bar nav a[aria-current] { border-bottom: 2px solid var(--tertiary); }
.menu-toggle { display: none; padding: .4rem .75rem; border: 1px solid #fff; border-radius: 6px;
  font-weight: 600; }
.layout { flex: 1; display: flex; min-height: 0; position: relative; }
.menu { width: 21rem; flex: none; overflow-y: auto; padding: 1rem; background: #fff;
  border-right: 1px solid #d5dbe1; }
.menu h1 { font-size: 1.2rem; margin: 0 0 .75rem; color: var(--primary); }
.menu label { display: block; font-weight: 600; margin: .75rem 0 .25rem; }
.menu input[type=text] { width: 100%; padding: .5rem .6rem; font: inherit;
  border: 1px solid #7b8794; border-radius: 6px; }
.menu .hint { display: block; font-weight: 400; font-size: .85rem; color: #52606d; }
.menu fieldset { border: 0; padding: 0; margin: .75rem 0 0; }
.menu legend { font-weight: 600; padding: 0; margin-bottom: .25rem; }
.menu .check { display: flex; align-items: center; gap: .5rem; font-weight: 400; margin: .3rem 0; }
.menu .check input { width: 1.1rem; height: 1.1rem; }
.actions { display: flex; align-items: center; gap: 1rem; margin-top: 1rem; }
.actions button { padding: .55rem 1.25rem; font: inherit; font-weight: 600; color: #fff;
  background: var(--primary); border: 0; border-radius: 6px; cursor: pointer; }
.actions button:hover { background: var(--secondary); }
.count { font-weight: 600; margin: 1.25rem 0 .5rem; }
.results { list-style: none; margin: 0; padding: 0; }
.results li { padding: .55rem 0; border-top: 1px solid #e4e7eb; }
.results a { font-weight: 600; text-decoration: none; }
.results a:hover { text-decoration: underline; }
.results .where { display: block; font-size: .9rem; color: #52606d; }
.pin { display: inline-flex; align-items: center; justify-content: center; width: 1.25rem;
  height: 1.25rem; border-radius: 50%; color: #fff; font-size: .7rem; font-weight: 700;
  flex: none; }
.rating { display: inline-flex; align-items: center; gap: .35rem; font-size: .9rem; }
.source { font-size: .8rem; color: #52606d; margin-top: 1.25rem; }
.sample { background: #fef3c7; border: 1px solid #b45309; border-radius: 6px; padding: .5rem; }
.close, .backdrop { display: none; }
.map { flex: 1; min-width: 0; }
.map iframe { width: 100%; height: 100%; border: 0; display: block; }
@media (max-width: 899px) {
  .menu-toggle { display: inline-block; }
  .bar nav { display: none; }
  .menu { position: absolute; z-index: 20; top: 0; bottom: 0; left: 0; width: min(21rem, 88vw);
    transform: translateX(-100%); visibility: hidden; transition: transform .2s, visibility .2s;
    box-shadow: 2px 0 12px rgba(0, 0, 0, .3); }
  .menu:target, .menu.open { transform: none; visibility: visible; }
  .menu:target ~ .backdrop, .menu.open ~ .backdrop { display: block; position: absolute;
    inset: 0; z-index: 10; background: rgba(0, 0, 0, .4); }
  .close { display: inline-block; float: right; font-weight: 600; }
}
@media (prefers-reduced-motion: reduce) { .menu { transition: none; } }
"""

# Opens and closes the menu on narrow screens; without it the links' #search-menu target does.
SCRIPT = """
(function () {
  var menu = document.getElementById('search-menu');
  var toggle = document.getElementById('menu-toggle');
  function set(open) {
    menu.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', String(open));
    if (open) { menu.querySelector('input').focus(); } else { toggle.focus(); }
  }
  toggle.addEventListener('click', function (e) { e.preventDefault(); set(true); });
  document.querySelectorAll('[data-close]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      e.preventDefault();
      if (location.hash) { history.replaceState(null, '', location.pathname + location.search); }
      set(false);
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && menu.classList.contains('open')) { set(false); }
  });
  // Arriving from the FastUI pages leaves their history entry on this document, so Back changes
  // the address without loading it; load it.
  window.addEventListener('popstate', function () {
    if (location.pathname !== '/map') { location.reload(); }
  });
})();
"""


def search_params(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The search fields of a query string, blanks dropped: what the API and the frame get."""
    return [(k, v.strip()) for k, v in pairs if k in SEARCH_FIELDS and v.strip()]


def rating_badge(rating: str) -> str:
    return (
        f'<span class="rating"><span class="pin" style="background:{COLOURS[rating]}" '
        f'aria-hidden="true">{INITIALS[rating]}</span>{escape(rating)}</span>'
    )


def source_note(dataset: CareHomeDataset | None) -> str:
    if dataset is None:
        return ""
    if dataset.source == "sample":
        return (
            '<p class="source sample">Sample data: these homes are made up. Load the Care '
            "Quality Commission's data with <code>uv run task ingest</code>.</p>"
        )
    as_of = f", published {dataset.as_of:%-d %B %Y}" if dataset.as_of else ""
    return f'<p class="source">{escape(ATTRIBUTION)} Data{as_of}.</p>'


def render(
    site: Site,
    params: list[tuple[str, str]],
    page: CareHomePage,
    icon: str | None = None,
    focus: str = "",
) -> str:
    """The whole page. `params` are the current search fields, `page` the API's matches, and
    `focus` the `location_id` of a home the map should open on."""
    value = {k: v for k, v in params if k != "rating"}
    chosen = {v for k, v in params if k == "rating"}
    query = urlencode([*params, *([("focus", focus)] if focus else [])])
    name = escape(site.brand.name or "")

    def field(key: str, label: str, hint: str, complete: str) -> str:
        longest = 10 if key == "postcode" else 100  # the API's own limits
        return (
            f'<label for="f-{key}">{label}<span class="hint">{hint}</span></label>'
            f'<input type="text" id="f-{key}" name="{key}" maxlength="{longest}" '
            f'autocomplete="{complete}" value="{escape(value.get(key, ""), quote=True)}">'
        )

    checks = "".join(
        f'<label class="check"><input type="checkbox" name="rating" value="{escape(r)}"'
        f"{' checked' if r in chosen else ''}>{rating_badge(r)}</label>"
        for r in RATINGS
    )
    results = "".join(
        f'<li><a href="/map?{escape(urlencode([*params, ("focus", h.location_id)]))}">'
        f"{escape(h.name)}</a>"
        f'<span class="where">{escape(", ".join(p for p in (h.town, h.postcode) if p))}</span>'
        f"{rating_badge(h.rating)}</li>"
        for h in page.items
    )
    more = (
        f'<p class="hint">Showing the first {len(page.items)} here; the map shows all '
        f"{page.total:,}.</p>"
        if page.total > len(page.items)
        else ""
    )
    homes = "care home" if page.total == 1 else "care homes"
    favicon = f'<link rel="icon" href="{escape(icon)}">' if icon else ""
    theme = site.theme
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Map · {name}</title>
{favicon}
<style>:root {{ --primary: {theme.primary}; --secondary: {theme.secondary};
  --tertiary: {theme.tertiary}; --font: {escape(theme.font_family, quote=False)}; }}
{CSS}</style>
</head>
<body>
<header class="bar">
  <a class="menu-toggle" id="menu-toggle" href="#search-menu" role="button"
     aria-controls="search-menu" aria-expanded="false">Search</a>
  <a class="brand" href="/">{name}</a>
  <nav aria-label="Site">
    <a href="/">{escape(site.welcome.title)}</a>
    <a href="/map" aria-current="page">Map</a>
    <a href="/about">{escape(site.about.title)}</a>
  </nav>
</header>
<div class="layout">
  <aside class="menu" id="search-menu" aria-label="Search care homes">
    <a class="close" href="#" data-close>Close</a>
    <h1>Find a care home</h1>
    <form method="get" action="/map" role="search">
      {field("name", "Name", "All or part of the home's name", "off")}
      {field("location", "Location", "Town, county, council area or region", "address-level2")}
      {field("postcode", "Postcode", "The start is enough, such as SA73", "postal-code")}
      <fieldset><legend>Latest CQC rating</legend>{checks}</fieldset>
      <div class="actions"><button type="submit">Search</button><a href="/map">Clear</a></div>
    </form>
    <p class="count" role="status" data-testid="count">{page.total:,} {homes}</p>
    <ol class="results" data-testid="results">{results}</ol>
    {more}
    {source_note(page.dataset)}
  </aside>
  <a class="backdrop" href="#" data-close aria-label="Close search" tabindex="-1"></a>
  <main class="map">
    <iframe title="Map of care homes, coloured by latest CQC rating"
            src="/map/frame{"?" + escape(query) if query else ""}"></iframe>
  </main>
</div>
<script>{SCRIPT}</script>
</body>
</html>"""

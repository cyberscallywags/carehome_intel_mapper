"""Shared Pydantic models: the contract between API, UI, admin and tests."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class ItemIn(BaseModel):
    """What a client sends to create an item."""

    name: str = Field(min_length=1, max_length=200, examples=["Castell"])


class Item(ItemIn):
    """A stored item, as returned by the API."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = Field(None, description="`id` of the member who added it.")


class Health(BaseModel):
    """API status, where items are stored, and whether Neo4j is reachable."""

    status: str
    env: str
    storage: Literal["neo4j", "memory"] = "neo4j"
    neo4j: bool


# ---------------------------------------------------------------- care homes
# Read-only records built from the Care Quality Commission's public data (app.carehomes).

Rating = Literal["Outstanding", "Good", "Requires improvement", "Inadequate", "Not rated"]
RATINGS: tuple[Rating, ...] = (
    "Outstanding",
    "Good",
    "Requires improvement",
    "Inadequate",
    "Not rated",
)


# The five questions CQC asks of every service; each gets its own rating.
KEY_QUESTIONS = ("Safe", "Effective", "Caring", "Responsive", "Well-led")


class CareHome(BaseModel):
    """One care home registered with the Care Quality Commission (CQC), with its latest
    ratings. Built from CQC's location record; fields the source does not carry stay empty
    (the monthly spreadsheet has no key-question ratings or inspection date, the API has both).
    """

    location_id: str = Field(description="CQC location id.", examples=["1-1000210669"])
    name: str
    also_known_as: str = ""
    brand_name: str = Field("", description="The group the home trades under, if any.")
    address: str = Field("", description="Street address, on one line.")
    town: str = ""
    county: str = ""
    postcode: str = Field("", examples=["SA73 2JA"])
    local_authority: str = ""
    region: str = ""
    constituency: str = Field("", description="Parliamentary constituency.")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    rating: Rating = Field(
        "Not rated",
        description="Latest overall CQC rating. `Not rated` covers every home with no "
        "published rating, whatever the reason.",
    )
    rating_published: date | None = Field(
        None, description="When the report behind the rating was published."
    )
    rating_safe: Rating | None = Field(None, description="Key question: is the home safe?")
    rating_effective: Rating | None = Field(None, description="Key question: is it effective?")
    rating_caring: Rating | None = Field(None, description="Key question: is it caring?")
    rating_responsive: Rating | None = Field(
        None, description="Key question: is it responsive to people's needs?"
    )
    rating_well_led: Rating | None = Field(None, description="Key question: is it well-led?")
    last_inspected: date | None = Field(None, description="Date of the last inspection.")
    registered: date | None = Field(None, description="When the home was registered with CQC.")
    beds: int | None = Field(None, ge=0, description="Registered care home beds.")
    inspection_category: str = Field(
        "", description="CQC's primary inspection category, e.g. `Residential social care`."
    )
    service_types: list[str] = Field(
        [], description="CQC service types, e.g. `Care home service with nursing`."
    )
    specialisms: list[str] = Field(
        [], description="Who the home cares for, e.g. `Dementia`, `Physical disabilities`."
    )
    regulated_activities: list[str] = Field([], description="What the home is registered to do.")
    phone: str = ""
    website: str = ""
    provider_id: str = ""
    provider_name: str = ""

    @property
    def key_question_ratings(self) -> dict[str, Rating]:
        """The key questions CQC has rated, in CQC's order: `{"Safe": "Good", ...}`."""
        rated = {q: getattr(self, f"rating_{q.lower().replace('-', '_')}") for q in KEY_QUESTIONS}
        return {question: rating for question, rating in rated.items() if rating}

    @property
    def cqc_url(self) -> str:
        """The home's page on the CQC website, with its inspection reports."""
        return f"https://www.cqc.org.uk/location/{self.location_id}"


class CareHomeDataset(BaseModel):
    """Where the care home records being served came from."""

    source: Literal["sample", "cqc-directory", "cqc-api"] = Field(
        description="`sample` is made-up demonstration data, never real homes."
    )
    name: str = Field(description="File name or API address the records were read from.")
    as_of: date | None = Field(None, description="Date CQC published the data, when known.")
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    count: int = 0


class CareHomePage(BaseModel):
    """What `GET /carehomes` returns: the homes matching a search, and how many there are in
    all."""

    total: int
    items: list[CareHome]
    dataset: CareHomeDataset | None = None


# ---------------------------------------------------------------- sign-on
# Mock sign-on (app.api.auth) issues these; a real identity provider would issue the same shapes.

Role = Literal["member", "admin"]
Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+$", examples=["ada@example.org"])]


class Member(BaseModel):
    """A signed-in person, as the API and both frontends see them."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", examples=["ada"])
    name: str
    email: Email
    role: Role = "member"


class LoginIn(BaseModel):
    """Credentials for `POST /auth/login`. In mock mode every demo member shares one password."""

    email: Email
    password: str = Field(min_length=1, examples=["demo"], json_schema_extra={"format": "password"})


class Session(BaseModel):
    """What `POST /auth/login` returns: send `token` as `Authorization: Bearer <token>`."""

    token: str
    member: Member
    expires_at: datetime


class AuthInfo(BaseModel):
    """How the frontends should offer sign-on, added to `GET /site` by the API."""

    mode: Literal["off", "mock"]
    demo_users: list[Member] = []  # mock mode only: the "Sign in as…" shortcuts


class AskIn(BaseModel):
    """A natural-language question for the agent."""

    question: str = Field(min_length=1, max_length=2000, examples=["What items exist?"])


class AskOut(BaseModel):
    """The agent's answer."""

    answer: str


# ---------------------------------------------------------------- site manifest
# One JSON document (content/site.json) describes the brand, theme and pages. The API serves
# it at GET /site; the FastUI frontend and the mobile app both render from it.

HexColour = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]

# Routes the frontends own; a content page may not shadow them.
RESERVED_SLUGS = frozenset(
    {"welcome", "about", "items", "map", "sign-in", "login", "logout", "account"}
)


class Theme(BaseModel):
    """Brand colours; Ionic colour variables on mobile, Bootstrap overrides on web."""

    primary: HexColour
    secondary: HexColour
    tertiary: HexColour
    font_family: str = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"


class Brand(BaseModel):
    """Project name and tagline, and the collective behind it. Name and collective default to
    brand.toml's when the manifest leaves them out."""

    name: str | None = None
    tagline: str
    collective: str | None = None
    collective_url: str | None = None


class SectionItem(BaseModel):
    """One entry in a list, steps or cards section."""

    title: str
    body: str | None = None
    icon: str | None = None
    url: str | None = None


class Section(BaseModel):
    """A block of a page, rendered the same way on web and mobile."""

    # text: heading + body. list/steps: bullet or numbered items. cards: a grid of items.
    kind: Literal["text", "list", "steps", "cards"] = "text"
    heading: str | None = None
    body: str | None = None
    items: list[SectionItem] = []


class ContentPage(BaseModel):
    """A page built from sections: welcome, about, or a sidebar page at /p/<slug>."""

    slug: Slug
    title: str
    icon: str = "document-text-outline"
    summary: str | None = None
    sections: list[Section] = []


class Site(BaseModel):
    """The site manifest served at GET /site: everything the frontends render."""

    brand: Brand
    theme: Theme
    welcome: ContentPage
    about: ContentPage
    pages: list[ContentPage] = []  # project pages listed in the sidebar, in order
    # Deployment-specific, so it comes from the DOCS_URL setting, not site.json.
    docs_url: str | None = None
    # Added by the API from the sign-on settings; never stored in site.json.
    auth: AuthInfo | None = None

    @model_validator(mode="after")
    def _unique_page_slugs(self) -> Site:
        slugs = [p.slug for p in self.pages]
        if clash := RESERVED_SLUGS.intersection(slugs):
            raise ValueError(f"page slugs are reserved: {sorted(clash)}")
        if len(slugs) != len(set(slugs)):
            raise ValueError("page slugs must be unique")
        return self

    def page(self, slug: str) -> ContentPage | None:
        return next((p for p in self.pages if p.slug == slug), None)

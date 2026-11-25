"""CQC's own record shapes, as Pydantic models: one location and one provider exactly as the
syndication API returns them (CQC's `Syndication_Location_Id.json` and
`Syndication_Provider_Id.json` schemas), and the paged lists of ids.

They are read models for someone else's data, so they are forgiving: every field is optional,
unknown fields are kept out of the way rather than rejected, and a date CQC has written oddly
becomes None instead of failing the record. Field names are ours (snake_case); each reads
CQC's camelCase name. `care_home_from` turns a location into the app's own `CareHome`.
"""

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.models import KEY_QUESTIONS, CareHome, Rating

RATINGS: dict[str, Rating] = {
    "outstanding": "Outstanding",
    "good": "Good",
    "requires improvement": "Requires improvement",
    "inadequate": "Inadequate",
}


def to_rating(text: str | None) -> Rating:
    """CQC's rating text as one of our five bands. Everything that is not one of the four
    ratings (blank, `Not rated`, `Insufficient evidence to rate`, ...) is `Not rated`."""
    return RATINGS.get(" ".join((text or "").lower().split()), "Not rated")


def to_date(value: object) -> date | None:
    """A date from the forms CQC uses (`2025-06-20`, `2025-06-20T00:00:00Z`, `20/06/2025`,
    `20 June 2025`), or None when it is blank or unreadable."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for layout, length in (("%Y-%m-%d", 10), ("%d/%m/%Y", 10), ("%d-%m-%Y", 10)):
        try:
            return datetime.strptime(text[:length], layout).date()
        except ValueError:
            continue
    for layout in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, layout).date()
        except ValueError:
            continue
    return None


def to_website(text: str | None) -> str:
    """A web address safe to use as a link: http(s) only, with the scheme added when CQC's
    record leaves it out."""
    text = (text or "").strip()
    if not text or " " in text:
        return ""
    if text.lower().startswith(("http://", "https://")):
        return text
    return "" if ":" in text.split("/")[0] else f"https://{text}"


CqcDate = Annotated[date | None, BeforeValidator(to_date)]


class CqcModel(BaseModel):
    """Base for CQC's shapes: camelCase on the wire, nothing required, extras ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class KeyQuestionRating(CqcModel):
    """The rating for one of the five key questions: Safe, Effective, Caring, Responsive,
    Well-led."""

    name: str = ""
    rating: str = ""
    report_date: CqcDate = None
    report_link_id: str | None = None
    organisation_id: str | None = None


class UseOfResources(CqcModel):
    """NHS trusts only: how well the trust uses its resources."""

    summary: str | None = None
    use_of_resources_rating: str | None = None
    combined_quality_rating: str | None = None
    report_date: CqcDate = None
    report_link_id: str | None = None
    organisation_id: str | None = None


class OverallRating(CqcModel):
    rating: str | None = None
    report_date: CqcDate = None
    report_link_id: str | None = None
    organisation_id: str | None = None
    # The historic-ratings schema declares this a string; current ratings send an object.
    use_of_resources: UseOfResources | str | None = None
    key_question_ratings: list[KeyQuestionRating] = []


class ServiceRating(CqcModel):
    """The rating of one service at a location that offers several."""

    name: str = ""
    rating: str = ""
    report_date: CqcDate = None
    report_link_id: str | None = None
    organisation_id: str | None = None
    key_question_ratings: list[KeyQuestionRating] = []


class CurrentRatings(CqcModel):
    overall: OverallRating | None = None
    report_date: CqcDate = None
    service_ratings: list[ServiceRating] = []


class HistoricRating(CqcModel):
    """The ratings from one earlier report."""

    report_link_id: str | None = None
    organisation_id: str | None = None
    report_date: CqcDate = None
    overall: OverallRating | None = None
    service_ratings: list[ServiceRating] = []


class RelatedDocument(CqcModel):
    document_uri: str | None = None
    document_type: str | None = None


class InspectionLocation(CqcModel):
    location_id: str = ""


class Report(CqcModel):
    """A published inspection report. `report_uri` is a path under the API's base address."""

    link_id: str = ""
    report_date: CqcDate = None
    report_uri: str = ""
    report_type: str | None = None
    first_visit_date: CqcDate = None
    related_documents: list[RelatedDocument] = []
    inspection_locations: list[InspectionLocation] = []  # provider reports only


class UnpublishedReport(CqcModel):
    first_visit_date: CqcDate = None


class Person(CqcModel):
    """A registered manager or nominated individual, as CQC publishes them."""

    person_title: str | None = None
    person_given_name: str | None = None
    person_family_name: str | None = None
    person_roles: list[str] = []


class RegulatedActivity(CqcModel):
    """Something the service is registered to do, e.g. `Accommodation for persons who require
    nursing or personal care`."""

    name: str = ""
    code: str = ""
    contacts: list[Person] = []  # locations
    nominated_individual: Person | None = None  # providers


class GacServiceType(CqcModel):
    """A service type, e.g. `Nursing homes` / `Care home service with nursing`."""

    name: str = ""
    description: str = ""


class InspectionCategory(CqcModel):
    code: str = ""
    primary: str | None = None  # "true" on the location's main category
    name: str = ""


class Specialism(CqcModel):
    """Who the service cares for, e.g. `Dementia`, `Caring for adults over 65 yrs`."""

    name: str = ""


class InspectionArea(CqcModel):
    inspection_area_id: str = ""
    inspection_area_name: str = ""
    status: str = ""
    end_date: CqcDate = None
    superseded_by: list[str] = []
    latest_globally_superseded_by: list[str] = []


class ProviderInspectionAreaReport(CqcModel):
    inspection_id: str = ""
    report_link_id: str = ""
    provider_id: str = ""
    location_id: str = ""


class ProviderInspectionArea(CqcModel):
    inspection_area_id: str = ""
    reports: list[ProviderInspectionAreaReport] = []


class Relationship(CqcModel):
    """A link to a location this one replaced or was replaced by."""

    related_location_id: str | None = None
    related_location_name: str | None = None
    type: str | None = None
    reason: str | None = None


class LastInspection(CqcModel):
    date: CqcDate = None


class LastReport(CqcModel):
    publication_date: CqcDate = None


class AssessmentServiceGroup(CqcModel):
    assessment_service_id: str = ""
    assessment_service_name: str = ""
    status: str = ""
    start_date: CqcDate = None
    end_date: CqcDate = None


class AssessedKeyQuestion(CqcModel):
    """A key question under the single assessment framework, with its commentary and score.
    (`percengtage_score` is CQC's spelling.)"""

    name: str = ""
    rating: str = ""
    commentary: str | None = None
    commentary_date: CqcDate = None
    narrative: str | None = None
    percengtage_score: str | None = None
    topicareas: list[dict[str, Any]] = []  # quality statements; kept as CQC sends them


class AssessmentServiceGroupRating(CqcModel):
    title: str = ""
    assessment_date: CqcDate = None
    assessment_plan_status: str | None = None
    assessment_plan_id: str | None = None
    name: str = ""
    rating: str = ""
    status: str | None = None
    commentary: str | None = None
    commentary_date: CqcDate = None
    narrative: str | None = None
    overall_people_experience: str | None = None
    overall_people_experience_date: CqcDate = None
    assessor_visit_dates: list[dict[str, Any]] = []
    key_question_ratings: list[AssessedKeyQuestion] = []


class AssessmentRatings(CqcModel):
    asg_ratings: list[AssessmentServiceGroupRating] = []


class Assessment(CqcModel):
    """An assessment under CQC's single assessment framework (2024 onwards)."""

    title: str | None = None
    assessment_date: CqcDate = None
    assessment_plan_status: str | None = None
    assessment_plan_published_date_time: datetime | None = None
    ratings: AssessmentRatings | None = None


class CqcOrganisation(CqcModel):
    """What a location and a provider have in common."""

    provider_id: str = ""
    organisation_type: str | None = None
    type: str | None = None
    name: str = ""
    also_known_as: str | None = None
    brand_id: str | None = None
    brand_name: str | None = None
    ods_code: str | None = None
    uprn: str | None = None
    registration_status: str | None = None
    registration_date: CqcDate = None
    deregistration_date: CqcDate = None
    website: str | None = None
    postal_address_line1: str | None = Field(None, alias="postalAddressLine1")
    postal_address_line2: str | None = Field(None, alias="postalAddressLine2")
    postal_address_town_city: str | None = None
    postal_address_county: str | None = None
    region: str | None = None
    postal_code: str | None = None
    onspd_latitude: float | None = None
    onspd_longitude: float | None = None
    onspd_icb_code: str | None = None
    onspd_icb_name: str | None = None
    main_phone_number: str | None = None
    inspection_directorate: str | None = None
    constituency: str | None = None
    local_authority: str | None = None
    last_inspection: LastInspection | None = None
    last_report: LastReport | None = None
    relationships: list[Relationship] = []
    regulated_activities: list[RegulatedActivity] = []
    inspection_categories: list[InspectionCategory] = []
    inspection_areas: list[InspectionArea] = []
    current_ratings: CurrentRatings | None = None
    historic_ratings: list[HistoricRating] = []
    unpublished_reports: list[UnpublishedReport] = []
    reports: list[Report] = []
    assessment_service_group: list[AssessmentServiceGroup] = []
    assessment: list[Assessment] = []


class CqcLocation(CqcOrganisation):
    """One location: a place where a provider delivers care (`GET /locations/{id}`)."""

    location_id: str = ""
    onspd_ccg_code: str | None = None
    onspd_ccg_name: str | None = None
    ods_ccg_code: str | None = None
    ods_ccg_name: str | None = None
    dormancy: str | None = None
    dormancy_start_date: CqcDate = None
    dormancy_end_date: CqcDate = None
    number_of_beds: int | None = None
    registered_manager_absent_date: CqcDate = None
    care_home: str | None = None  # "Y" or "N"
    location_types: list[dict[str, Any]] = []
    gac_service_types: list[GacServiceType] = []
    specialisms: list[Specialism] = []
    provider_inspection_areas: list[ProviderInspectionArea] = []

    @property
    def is_care_home(self) -> bool:
        return (self.care_home or "").upper() == "Y"

    @property
    def is_registered(self) -> bool:
        return (self.registration_status or "Registered") == "Registered"


class CqcProvider(CqcOrganisation):
    """One provider: the organisation or person registered to run locations
    (`GET /providers/{id}`)."""

    location_ids: list[str] = []
    ownership_type: str | None = None
    companies_house_number: str | None = None
    charity_number: str | None = None
    contacts: list[dict[str, Any]] = []


class LocationSummary(CqcModel):
    """An entry in `GET /locations`: the id, name and postcode only."""

    location_id: str
    location_name: str = ""
    post_code: str | None = None


class ProviderSummary(CqcModel):
    provider_id: str
    provider_name: str = ""


class Page(CqcModel):
    """The paging fields of `GET /locations` and `GET /providers`."""

    total: int = 0
    page: int = 1
    per_page: int = 0
    total_pages: int = 1
    next_page_uri: str | None = None


class LocationPage(Page):
    locations: list[LocationSummary] = []


class ProviderPage(Page):
    providers: list[ProviderSummary] = []


def key_question_ratings(ratings: list[KeyQuestionRating]) -> dict[str, Rating]:
    """`{"rating_safe": "Good", ...}` for the key questions CQC has rated."""
    found = {q.name.strip().lower(): to_rating(q.rating) for q in ratings}
    return {
        f"rating_{question.lower().replace('-', '_')}": found[question.lower()]
        for question in KEY_QUESTIONS
        if question.lower() in found
    }


def care_home_from(location: CqcLocation, provider_name: str = "") -> CareHome | None:
    """The app's care home for a CQC location, or None when the location is not a registered
    care home or CQC holds no coordinates for it (so it cannot be put on the map)."""
    if not (location.is_care_home and location.is_registered and location.location_id):
        return None
    if location.onspd_latitude is None or location.onspd_longitude is None:
        return None
    overall = (location.current_ratings.overall if location.current_ratings else None) or (
        OverallRating()
    )
    primary = next(
        (c for c in location.inspection_categories if (c.primary or "").lower() == "true"),
        next(iter(location.inspection_categories), None),
    )
    address = (location.postal_address_line1, location.postal_address_line2)
    return CareHome(
        location_id=location.location_id,
        name=location.name,
        also_known_as=location.also_known_as or "",
        brand_name=location.brand_name or "",
        address=", ".join(part.strip() for part in address if part and part.strip()),
        town=location.postal_address_town_city or "",
        county=location.postal_address_county or "",
        postcode=(location.postal_code or "").upper(),
        local_authority=location.local_authority or "",
        region=location.region or "",
        constituency=location.constituency or "",
        latitude=location.onspd_latitude,
        longitude=location.onspd_longitude,
        rating=to_rating(overall.rating),
        rating_published=overall.report_date,
        **key_question_ratings(overall.key_question_ratings),
        last_inspected=location.last_inspection.date if location.last_inspection else None,
        registered=location.registration_date,
        beds=location.number_of_beds,
        inspection_category=primary.name if primary else "",
        service_types=[s.description or s.name for s in location.gac_service_types],
        specialisms=[s.name for s in location.specialisms if s.name],
        regulated_activities=[a.name for a in location.regulated_activities if a.name],
        phone=location.main_phone_number or "",
        website=to_website(location.website),
        provider_id=location.provider_id,
        provider_name=provider_name,
    )

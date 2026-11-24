"""CQC's location and provider records as models, and the care home built from a location."""

from datetime import date

from app.carehomes.cqc_models import (
    CqcLocation,
    CqcProvider,
    LocationPage,
    care_home_from,
    to_date,
)
from app.carehomes.mapview import render_map

# A location in the shape of CQC's Syndication_Location_Id.json schema.
LOCATION = {
    "locationId": "1-101",
    "providerId": "1-9",
    "organisationType": "Location",
    "type": "Social Care Org",
    "name": "Ty Example",
    "alsoKnownAs": "The Example",
    "brandName": "BRAND Example Care",
    "registrationStatus": "Registered",
    "registrationDate": "2011-01-17",
    "numberOfBeds": 42,
    "website": "www.example.org",
    "postalAddressLine1": "1 Example Street",
    "postalAddressLine2": "Redland",
    "postalAddressTownCity": "Bristol",
    "region": "South West",
    "postalCode": "bs1 9zz",
    "onspdLatitude": 51.454513,
    "onspdLongitude": -2.58791,
    "careHome": "Y",
    "mainPhoneNumber": "01234567890",
    "constituency": "Bristol Central",
    "localAuthority": "Bristol, City of",
    "lastInspection": {"date": "2025-05-06"},
    "lastReport": {"publicationDate": "2025-06-20"},
    "regulatedActivities": [
        {
            "name": "Accommodation for persons who require nursing or personal care",
            "code": "RA2",
            "contacts": [
                {
                    "personTitle": "Ms",
                    "personGivenName": "A",
                    "personFamilyName": "Manager",
                    "personRoles": ["Registered Manager"],
                }
            ],
        }
    ],
    "gacServiceTypes": [{"name": "Nursing homes", "description": "Care home service with nursing"}],
    "inspectionCategories": [
        {"code": "S2", "name": "Community based adult social care services"},
        {"code": "S1", "primary": "true", "name": "Residential social care"},
    ],
    "specialisms": [{"name": "Dementia"}, {"name": "Caring for adults over 65 yrs"}],
    "currentRatings": {
        "overall": {
            "rating": "Requires improvement",
            "reportDate": "2025-06-20",
            "reportLinkId": "abc",
            "keyQuestionRatings": [
                {
                    "name": "Safe",
                    "rating": "Requires improvement",
                    "reportDate": "2025-06-20",
                    "reportLinkId": "abc",
                },
                {
                    "name": "Effective",
                    "rating": "Good",
                    "reportDate": "2025-06-20",
                    "reportLinkId": "abc",
                },
                {
                    "name": "Caring",
                    "rating": "Good",
                    "reportDate": "2025-06-20",
                    "reportLinkId": "abc",
                },
                {
                    "name": "Responsive",
                    "rating": "Good",
                    "reportDate": "2025-06-20",
                    "reportLinkId": "abc",
                },
                {
                    "name": "Well-led",
                    "rating": "Requires improvement",
                    "reportDate": "2025-06-20",
                    "reportLinkId": "abc",
                },
            ],
        },
        "reportDate": "2025-06-20",
    },
    "historicRatings": [
        {
            "reportLinkId": "old",
            "reportDate": "2022-03-01",
            "overall": {
                "rating": "Good",
                "keyQuestionRatings": [{"name": "Safe", "rating": "Good"}],
            },
        }
    ],
    "reports": [
        {
            "linkId": "abc",
            "reportDate": "2025-06-20",
            "reportUri": "/reports/abc",
            "relatedDocuments": [
                {"documentUri": "/reports/abc/1", "documentType": "Use of Resources"}
            ],
        }
    ],
    "assessment": [
        {
            "title": "Assessment",
            "assessmentDate": "2025-05-06",
            "assessmentPlanStatus": "Published",
            "assessmentPlanPublishedDateTime": "2025-06-20T09:00:00Z",
            "ratings": {
                "asgRatings": [
                    {
                        "name": "Overall",
                        "rating": "Requires improvement",
                        "keyQuestionRatings": [
                            {
                                "name": "Safe",
                                "rating": "Requires improvement",
                                "percengtageScore": "58",
                            }
                        ],
                    }
                ]
            },
        }
    ],
    "somethingCqcAddsLater": {"ignored": True},
}


def test_location_reads_cqcs_shape():
    location = CqcLocation.model_validate(LOCATION)
    assert location.postal_address_line1 == "1 Example Street"
    assert location.registration_date == date(2011, 1, 17)
    assert location.last_inspection.date == date(2025, 5, 6)
    assert location.regulated_activities[0].contacts[0].person_roles == ["Registered Manager"]
    assert location.current_ratings.overall.key_question_ratings[4].name == "Well-led"
    assert location.historic_ratings[0].overall.rating == "Good"
    assert location.reports[0].related_documents[0].document_type == "Use of Resources"
    asg = location.assessment[0].ratings.asg_ratings[0]
    assert asg.key_question_ratings[0].percengtage_score == "58"
    assert location.is_care_home and location.is_registered


def test_location_tolerates_an_empty_record_and_odd_dates():
    location = CqcLocation.model_validate({"registrationDate": "soon", "lastInspection": {}})
    assert location.registration_date is None
    assert location.location_id == "" and not location.is_care_home
    assert to_date("2025-06-20T00:00:00Z") == to_date("20/06/2025") == to_date("20 June 2025")


def test_care_home_from_a_location():
    home = care_home_from(CqcLocation.model_validate(LOCATION), provider_name="Example Care Ltd")
    assert home.model_dump() == {
        "location_id": "1-101",
        "name": "Ty Example",
        "also_known_as": "The Example",
        "brand_name": "BRAND Example Care",
        "address": "1 Example Street, Redland",
        "town": "Bristol",
        "county": "",
        "postcode": "BS1 9ZZ",
        "local_authority": "Bristol, City of",
        "region": "South West",
        "constituency": "Bristol Central",
        "latitude": 51.454513,
        "longitude": -2.58791,
        "rating": "Requires improvement",
        "rating_published": date(2025, 6, 20),
        "rating_safe": "Requires improvement",
        "rating_effective": "Good",
        "rating_caring": "Good",
        "rating_responsive": "Good",
        "rating_well_led": "Requires improvement",
        "last_inspected": date(2025, 5, 6),
        "registered": date(2011, 1, 17),
        "beds": 42,
        "inspection_category": "Residential social care",
        "service_types": ["Care home service with nursing"],
        "specialisms": ["Dementia", "Caring for adults over 65 yrs"],
        "regulated_activities": ["Accommodation for persons who require nursing or personal care"],
        "phone": "01234567890",
        "website": "https://www.example.org",
        "provider_id": "1-9",
        "provider_name": "Example Care Ltd",
    }
    assert list(home.key_question_ratings) == [
        "Safe",
        "Effective",
        "Caring",
        "Responsive",
        "Well-led",
    ]


def test_only_registered_care_homes_with_coordinates_become_care_homes():
    for change in (
        {"careHome": "N"},
        {"registrationStatus": "Deregistered"},
        {"onspdLatitude": None},
        {"locationId": ""},
    ):
        assert care_home_from(CqcLocation.model_validate(LOCATION | change)) is None, change
    unrated = care_home_from(CqcLocation.model_validate(LOCATION | {"currentRatings": None}))
    assert (unrated.rating, unrated.rating_safe, unrated.key_question_ratings) == (
        "Not rated",
        None,
        {},
    )


def test_provider_reads_cqcs_shape():
    provider = CqcProvider.model_validate(
        {
            "providerId": "1-9",
            "locationIds": ["1-101", "1-102"],
            "organisationType": "Provider",
            "ownershipType": "Organisation",
            "companiesHouseNumber": "01234567",
            "name": "Example Care Ltd",
            "registrationDate": "2010-10-01",
            "regulatedActivities": [
                {
                    "name": "Personal care",
                    "code": "RA1",
                    "nominatedIndividual": {"personGivenName": "A", "personFamilyName": "Person"},
                }
            ],
            "reports": [
                {
                    "linkId": "p1",
                    "reportDate": "2024-01-01",
                    "reportUri": "/reports/p1",
                    "reportType": "Provider",
                    "inspectionLocations": [{"locationId": "1-101"}],
                }
            ],
        }
    )
    assert provider.location_ids == ["1-101", "1-102"]
    assert provider.regulated_activities[0].nominated_individual.person_family_name == "Person"
    assert provider.reports[0].inspection_locations[0].location_id == "1-101"


def test_location_list_page():
    page = LocationPage.model_validate(
        {
            "total": 2,
            "page": 1,
            "perPage": 1,
            "totalPages": 2,
            "nextPageUri": "/locations?page=2",
            "locations": [
                {"locationId": "1-101", "locationName": "Ty Example", "postCode": "BS1 9ZZ"}
            ],
        }
    )
    assert (page.total_pages, page.locations[0].location_id) == (2, "1-101")


def test_map_popup_carries_the_key_question_ratings():
    home = care_home_from(CqcLocation.model_validate(LOCATION))
    html = render_map([home])
    assert "[2, 1, 1, 1, 2]" in html  # Safe .. Well-led as rating numbers
    assert "'Safe', 'Effective', 'Caring', 'Responsive', 'Well-led'" in html

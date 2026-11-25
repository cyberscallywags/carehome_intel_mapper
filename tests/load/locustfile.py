"""Locust load profile for the API. `task load` runs a 20s headless smoke;
`task load_ui` opens the Locust web UI on http://localhost:8089."""

import random

from locust import HttpUser, between, task


class ApiUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        """Pick some homes to open."""
        homes = self.client.get("/carehomes?limit=50", name="/carehomes?limit=").json()["items"]
        self.location_ids = [home["location_id"] for home in homes]

    @task(5)
    def list_care_homes(self) -> None:
        self.client.get("/carehomes?limit=20")

    @task(2)
    def one_care_home(self) -> None:
        if self.location_ids:
            location_id = random.choice(self.location_ids)  # noqa: S311 (not security)
            self.client.get(f"/carehomes/{location_id}", name="/carehomes/{location_id}")

    @task(3)
    def search_care_homes(self) -> None:
        self.client.get("/carehomes?location=london&limit=20", name="/carehomes?location=")

    @task(1)
    def care_home_map(self) -> None:
        self.client.get("/carehomes/map?postcode=LS1", name="/carehomes/map?postcode=")

    @task(1)
    def health(self) -> None:
        self.client.get("/health")

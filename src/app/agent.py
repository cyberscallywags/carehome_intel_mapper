"""The Pydantic AI agent behind `POST /ask`: it answers questions about care homes by searching
the same store the map uses.

With LLM_MODEL=test it uses the offline TestModel, so CI never needs an API key."""

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from app.carehomes.store import CareHomeStore, Query
from app.models import RATINGS

LISTED = 20  # homes a search hands the model


@dataclass
class Deps:
    store: CareHomeStore


def build_agent(model: str) -> Agent[Deps, str]:
    agent = Agent(
        model,
        deps_type=Deps,
        output_type=str,
        instructions=(
            "You answer questions about care homes in England from the Care Quality "
            "Commission's public data. Use the tools to look homes up, and say so when the "
            "data does not answer the question. Be brief."
        ),
    )

    @agent.tool
    async def dataset_summary(ctx: RunContext[Deps]) -> dict[str, object]:
        """Where the care home data came from, when it was published, how many homes there
        are, and how many hold each overall rating."""
        store = ctx.deps.store
        dataset = await store.dataset()
        ratings = {}
        for rating in RATINGS:
            ratings[rating], _ = await store.search(Query.of(ratings=[rating]), limit=1)
        return {
            "source": dataset.source if dataset else None,
            "published": dataset.as_of.isoformat() if dataset and dataset.as_of else None,
            "care_homes": dataset.count if dataset else 0,
            "by_rating": ratings,
        }

    @agent.tool
    async def search_care_homes(
        ctx: RunContext[Deps], name: str = "", location: str = "", postcode: str = ""
    ) -> dict[str, object]:
        """Care homes matching every part that is given: words in the home's name, words in
        its address, town, county, council area or region, and the start of its postcode.
        Returns the number of matches and the first few, each with its overall rating."""
        total, homes = await ctx.deps.store.search(Query.of(name, location, postcode), limit=LISTED)
        return {
            "total": total,
            "homes": [
                {"name": h.name, "town": h.town, "postcode": h.postcode, "rating": h.rating}
                for h in homes
            ],
        }

    return agent

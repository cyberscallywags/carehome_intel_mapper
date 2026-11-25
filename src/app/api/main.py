"""FastAPI service: the only thing that reads and writes the graph (besides admin).

Endpoint docstrings become the OpenAPI descriptions, which feed both the live Swagger UI
at /docs and the generated HTTP reference in the documentation site."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app import domain
from app.agent import Deps, build_agent
from app.api import auth
from app.carehomes import routes as carehomes
from app.carehomes.routes import Store
from app.carehomes.store import (
    CareHomeStore,
    MemoryCareHomeStore,
    Neo4jCareHomeStore,
    load_startup_data,
)
from app.config import get_settings
from app.content import get_site
from app.db import make_driver
from app.meta import get_meta
from app.models import AskIn, AskOut, Health, Site


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    auth.check_settings(settings)
    driver = make_driver(settings) if settings.storage == "neo4j" else None
    homes: CareHomeStore = (
        Neo4jCareHomeStore(driver, settings.neo4j_database) if driver else MemoryCareHomeStore()
    )
    await load_startup_data(homes, settings.carehomes_file)
    app.state.carehomes = homes
    app.state.driver = driver  # app.domain modules store their entities through it
    app.state.agent = build_agent(settings.llm_model)
    yield
    if driver:
        await driver.close()


meta = get_meta()
app = FastAPI(
    title=f"{meta.slug}-api",
    version=meta.version,
    description=f"Data, content and AI for every {meta.name} frontend. Talks to Neo4j.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
app.add_middleware(GZipMiddleware, minimum_size=2000)  # the full map is a few megabytes
app.include_router(auth.router)
app.include_router(carehomes.router)
for module in domain.modules():  # entities added with `uv run task new_entity`
    app.include_router(module.router)


@app.get("/health", response_model=Health, tags=["system"])
async def health(store: Store) -> Health:
    """Liveness, where care homes are stored, and Neo4j reachability. `degraded` means the API
    is up but its storage is not."""
    ok = await store.ping()
    storage = get_settings().storage
    return Health(
        status="ok" if ok else "degraded",
        env=get_settings().app_env,
        storage=storage,
        neo4j=ok and storage == "neo4j",
    )


@app.get("/site", response_model=Site, tags=["content"])
async def site() -> Site:
    """Brand, theme and pages shared by the web and mobile frontends, plus the docs link and how
    to sign on."""
    return get_site().model_copy(
        update={"docs_url": get_settings().docs_url or None, "auth": auth.auth_info()}
    )


@app.post("/ask", response_model=AskOut, tags=["ai"], dependencies=[Depends(auth.current_member)])
async def ask(body: AskIn, request: Request, store: Store) -> AskOut:
    """Answer a question about care homes with the Pydantic AI agent, which searches the same
    records as `GET /carehomes`. Needs a bearer token unless sign-on is off."""
    result = await request.app.state.agent.run(body.question, deps=Deps(store=store))
    return AskOut(answer=result.output)

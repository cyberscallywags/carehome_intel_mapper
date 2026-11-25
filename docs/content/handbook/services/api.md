# API

`src/app/api/main.py`: FastAPI, the only service that writes to the graph (besides
admin). Its endpoint docstrings become the OpenAPI descriptions, which feed both the live
Swagger UI at <http://localhost:8000/docs> and the [HTTP API](../../reference/http-api.md)
reference.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness and Neo4j reachability; `degraded` when the graph is down |
| `GET /site` | The [site manifest](../site-manifest.md) for the web and mobile frontends |
| `GET /carehomes`, `GET /carehomes/{location_id}` | Search the care homes, and read one |
| `GET /carehomes/map` | The Folium map of a search, which both frontends show in a frame |
| `POST /ask` | A Pydantic AI agent that answers questions by searching the care homes; needs a signed-in member |
| `POST /auth/login`, `GET /auth/me` | Mock sign-on: a bearer token for a demo member, and who a token belongs to |

## Sign-on

`app.api.auth` resolves the `Authorization: Bearer` header to a `Member`. A route that needs
one takes a `CurrentMember` argument (or `dependencies=[Depends(current_member)]`); a route
that only reads stays public. `require_role("admin")` limits a route to one role. See
[Sign-on](../sign-on.md) for the modes, the demo members and the move to a real provider.

## Entities

Every module in `src/app/domain/` (one per entity added with `uv run task new_entity <Name>`)
defines its models, its storage and a `router`, which the API includes: `GET /<plural>` lists
them, and `POST /<plural>` adds one for the signed-in member. With no Neo4j driver
(`STORAGE=memory`) a module stores its entities in memory. See
[Make it yours](../make-it-yours.md#5-model-the-domain).

## Graph access

`app.db.make_driver` opens the async Neo4j driver, and `app.carehomes.store` keeps the care
homes: `Neo4jCareHomeStore` as `(:CareHome)` nodes, or `MemoryCareHomeStore` with
`STORAGE=memory`, which needs no database (`uv run task dev` does this). Both satisfy the
`CareHomeStore` protocol, and `GET /health` says which is in use and whether it answers. On
start-up the API loads the snapshot written by `uv run task ingest`, or the made-up sample when
there is none. The unit tests' `FakeStore` builds on `MemoryCareHomeStore`.

## The agent

`app.agent.build_agent` builds a Pydantic AI agent with two tools over the care home store:
`dataset_summary` (where the data came from and how many homes hold each rating) and
`search_care_homes` (the same name, location and postcode search as `GET /carehomes`).
`LLM_MODEL=test` selects the offline `TestModel`, which calls every tool and echoes the
results, so tests need no API key. For a real model see [Configuration](../../reference/configuration.md).

## CORS

The web UI and the mobile web image reach the API server-side, so they need no CORS. A
native Capacitor build calls it directly from `capacitor://localhost`; list such origins in
`CORS_ORIGINS`. `Authorization` is an allowed header, so such a build can send its token.

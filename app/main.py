from fastapi import FastAPI
from app.database import init_db
from app.routes import router

app = FastAPI(
    title="Toroto Geospatial Interventions API",
    description="""
API for storing and querying geospatial interventions.

## Spatial Queries

- **Nearest neighbor** — closest intervention to a point (PostGIS KNN `<->`)
- **Within radius** — interventions within X km (PostGIS `ST_DWithin` + geography cast)
- **Within area** — interventions inside a polygon (PostGIS `ST_Within`)

All spatial operations use **SRID 4326 (WGS84)** with **GIST indexes** for performance.
    """,
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db
from app.routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("API starting...")
    yield
    print("API shutting down")

app = FastAPI(
    title="Toroto Geospatial Interventions API",
    description="API for geospatial queries with PostGIS",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}

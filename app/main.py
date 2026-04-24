from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db
from app.routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as e:
        print("DB init error:", e)

    yield
    print("Shutting down API")

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

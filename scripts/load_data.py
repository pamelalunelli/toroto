"""
Loads geospatial_interventions_dataset.json into PostGIS.
Idempotent: skips records that already exist (ON CONFLICT DO NOTHING).
Run once on startup via docker-compose command.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://toroto:toroto@localhost:5432/geospatial"
)
DATA_PATH = Path(__file__).parent.parent / "data" / "geospatial_interventions_dataset.json"


def load():
    engine = create_engine(DATABASE_URL)

    with open(DATA_PATH) as f:
        dataset = json.load(f)

    with engine.begin() as conn:
        # Enable PostGIS (safe to re-run)
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

        # Create tables
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS interventions (
                id                    TEXT PRIMARY KEY,
                subtype               TEXT,
                status                TEXT,
                project_id            TEXT,
                region                TEXT,
                geom                  geometry(POINT, 4326) NOT NULL,
                date                  TEXT,
                intervention_timestamp TIMESTAMPTZ,
                operator_id           TEXT,
                priority              TEXT,
                source                TEXT,
                quality_score         FLOAT,
                extra_metadata        JSONB,
                metrics               JSONB
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS areas (
                area_id  TEXT PRIMARY KEY,
                name     TEXT,
                geom     geometry(POLYGON, 4326) NOT NULL
            )
        """))

        # Spatial indexes (GIST)
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_interventions_geom
            ON interventions USING GIST (geom)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_areas_geom
            ON areas USING GIST (geom)
        """))

        # Load interventions
        inserted = 0
        for item in dataset["interventions"]:
            lat = item["coordinates"]["lat"]
            lon = item["coordinates"]["lon"]
            ts = item.get("timestamp")
            parsed_ts = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None

            result = conn.execute(text("""
                INSERT INTO interventions
                    (id, subtype, status, project_id, region, geom,
                     date, intervention_timestamp, operator_id, priority,
                     source, quality_score, extra_metadata, metrics)
                VALUES
                    (:id, :subtype, :status, :project_id, :region,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                     :date, :ts, :operator_id, :priority,
                     :source, :quality_score, CAST(:metadata AS jsonb), CAST(:metrics AS jsonb))
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": item["id"],
                "subtype": item.get("subtype"),
                "status": item.get("status"),
                "project_id": item.get("project_id"),
                "region": item.get("region"),
                "lat": lat,
                "lon": lon,
                "date": item.get("date"),
                "ts": parsed_ts,
                "operator_id": item.get("operator_id"),
                "priority": item.get("priority"),
                "source": item.get("source"),
                "quality_score": item.get("quality_score"),
                "metadata": json.dumps(item.get("metadata", {})),
                "metrics": json.dumps(item.get("metrics", {})),
            })
            inserted += result.rowcount

        # Load areas (polygons)
        for area in dataset["areas"]:
            geojson_str = json.dumps(area["geometry"])
            conn.execute(text("""
                INSERT INTO areas (area_id, name, geom)
                VALUES (
                    :area_id,
                    :name,
                    ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)
                )
                ON CONFLICT (area_id) DO NOTHING
            """), {
                "area_id": area["area_id"],
                "name": area["name"],
                "geojson": geojson_str,
            })

    print(f"✅ Loaded {inserted} interventions and {len(dataset['areas'])} areas into PostGIS")


if __name__ == "__main__":
    load()

# Geospatial Interventions API

REST API for storing and querying geospatial interventions, built with **FastAPI + PostgreSQL/PostGIS**.

## Live Components

- API Docs: http://localhost:8000/docs
- Map Demo: http://localhost:8501

Run:
docker-compose up --build

# API docs (Swagger UI)
open http://localhost:8000/docs
```

Data loads automatically on startup. The API is ready when you see:
```
✅ Loaded 130 interventions and 3 areas into PostGIS
```

---

## Architecture

```
┌─────────────┐     HTTP       ┌──────────────────────────────────────┐
│   Client    │ ────────────►  │  FastAPI                             │
└─────────────┘                │                                      │
                               │  routes.py   (HTTP layer)            │
                               │      │                               │
                               │  repository.py  (spatial queries)    │
                               │      │                               │
                               │  database.py  (connection/sessions)  │
                               └──────────────┬───────────────────────┘
                                              │ SQLAlchemy
                               ┌──────────────▼───────────────────────┐
                               │  PostgreSQL + PostGIS                │
                               │                                      │
                               │  interventions  (POINT geometry)     │
                               │  areas          (POLYGON geometry)   │
                               └──────────────────────────────────────┘
```

**Separation of concerns:**
| Layer | Responsibility |
|-------|---------------|
| `routes.py` | HTTP parsing, validation, response shaping |
| `repository.py` | All SQL and spatial query logic |
| `database.py` | Connection management, table/index creation |
| `models.py` | SQLAlchemy ORM table definitions |
| `schemas.py` | Pydantic input/output contracts |

This means the spatial logic can be tested independently of HTTP, and the storage engine can be swapped without touching routes.

---

## Database Model

```sql
interventions
├── id                TEXT PRIMARY KEY
├── subtype           TEXT              -- gavion, reforestacion, etc.
├── status            TEXT              -- in_progress, validated, etc.
├── project_id        TEXT
├── region            TEXT
├── geom              geometry(POINT, 4326)   ← PostGIS, GIST indexed
├── date              TEXT
├── intervention_timestamp  TIMESTAMPTZ
├── operator_id       TEXT
├── priority          TEXT
├── quality_score     FLOAT
├── extra_metadata    JSONB
└── metrics           JSONB             -- flexible per-subtype metrics

areas
├── area_id           TEXT PRIMARY KEY
├── name              TEXT
└── geom              geometry(POLYGON, 4326)  ← PostGIS, GIST indexed
```

**Why JSONB for metrics?** Different intervention subtypes have different metrics
(e.g., `area_m2` for gavion, `trees_planted` for reforestacion). A flexible JSONB
column avoids a wide sparse table or a complex EAV pattern.

**Why SRID 4326?** The input data is in WGS84 lat/lon, which is the universal standard
for GPS coordinates. All distance calculations cast to `geography` type to get accurate
geodesic distances in meters — not distorted planar degrees.

---

## Spatial Queries Explained

### 1. Nearest Neighbor — `GET /api/v1/interventions/nearest`

```sql
SELECT *, ST_Distance(geom::geography, ref::geography) AS distance_m
FROM interventions
ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
LIMIT 1
```

The `<->` operator is PostGIS's **KNN (K-Nearest Neighbor)** operator. It uses the
GIST index to find the closest geometry without scanning every row — O(log n) instead
of O(n). The `::geography` cast in `ST_Distance` computes the exact geodesic distance
in meters on the WGS84 ellipsoid.

**Example:**
```
GET /api/v1/interventions/nearest?lat=20.701&lon=-103.321
```

---

### 2. Within Radius — `GET /api/v1/interventions/within-radius`

```sql
SELECT *, ST_Distance(geom::geography, ref::geography) AS distance_m
FROM interventions
WHERE ST_DWithin(
    geom::geography,
    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
    :radius_m   -- in meters
)
ORDER BY distance_m
```

`ST_DWithin` with `::geography` cast checks **true geodesic distance** — critical near
the poles or at large scales where planar approximation breaks down. The GIST index
provides a fast bounding-box pre-filter before the exact distance check.

**Example:**
```
GET /api/v1/interventions/within-radius?lat=20.700&lon=-103.320&radius_km=5
GET /api/v1/interventions/within-radius?lat=20.700&lon=-103.320&radius_km=5&start_date=2026-03-01&end_date=2026-03-31
```

---

### 3. Within Area — `GET /api/v1/interventions/within-area/{area_id}`

```sql
SELECT i.*
FROM interventions i
JOIN areas a ON ST_Within(i.geom, a.geom)
WHERE a.area_id = :area_id
```

`ST_Within(point, polygon)` implements the **DE-9IM** spatial predicate — it returns
true only if the point is entirely inside the polygon boundary. PostGIS uses GIST indexes
on both geometries: a bounding-box intersection check first, then the exact topological test.

**Example:**
```
GET /api/v1/interventions/within-area/zone_a
GET /api/v1/interventions/within-area/zone_c?status=validated
```

---

## All Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/interventions/nearest` | Nearest neighbor |
| GET | `/api/v1/interventions/within-radius` | Within radius (km) |
| GET | `/api/v1/interventions/within-area/{area_id}` | Within polygon |
| GET | `/api/v1/areas` | List reference polygons |
| GET | `/api/v1/status-summary` | Count by status |
| GET | `/api/v1/subtype-by-region` | Count by region + subtype |
| GET | `/health` | Health check |

Full interactive docs at **http://localhost:8000/docs**

---

## Sample Queries from the Dataset

```bash
# "What intervention is closest to 20.701,-103.321?"
curl "http://localhost:8000/api/v1/interventions/nearest?lat=20.701&lon=-103.321"

# "Which interventions happened within 5km of 20.700,-103.320 during March 2026?"
curl "http://localhost:8000/api/v1/interventions/within-radius?lat=20.700&lon=-103.320&radius_km=5&start_date=2026-03-01&end_date=2026-03-31"

# "How many interventions are inside zone_c?"
curl "http://localhost:8000/api/v1/interventions/within-area/zone_c"

# "Count reforestacion interventions by region"
curl "http://localhost:8000/api/v1/subtype-by-region"
```

---

## Technical Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Database | PostgreSQL + PostGIS | Industry standard for production geospatial systems; GIST indexes, geography type, full OGC function library |
| Distance calculation | `::geography` cast | Geodesic accuracy on WGS84 ellipsoid; avoids degree-based distortion |
| Nearest neighbor | `<->` KNN operator | Uses GIST index directly — no full table scan |
| API framework | FastAPI | Async-ready, automatic OpenAPI docs, Pydantic validation |
| Metrics storage | JSONB | Flexible schema per intervention subtype without sparse columns |
| Containerization | Docker Compose | Zero-config local setup; mirrors production patterns |

---

## Limitations and Future Improvements

**Current limitations:**
- Filters in `_build_filters()` use string interpolation — should be fully parameterized
- No authentication layer
- No pagination on within-radius results (could return all 130 rows)
- History/audit log not implemented (would need a `intervention_history` table + triggers)

**Scale path:**
- Add `CLUSTER interventions USING idx_interventions_geom` for physical ordering by location
- Partition table by `region` or `date` for very large datasets
- Add read replicas behind a connection pool (PgBouncer) for query scaling
- Replace Docker Compose with Cloud Run + Cloud SQL for serverless deployment on GCP

---

## Part 3 – AI Query Layer (Design)

### Architecture

```
User (natural language)
        │
        ▼
┌───────────────────┐
│   LLM Layer       │  Claude / GPT-4o
│  (intent parser)  │  System prompt with schema + spatial function catalog
└────────┬──────────┘
         │  structured intent JSON
         ▼
┌───────────────────┐
│  Query Router     │  Maps intent → predefined spatial function
└────────┬──────────┘
         │  validated parameters
         ▼
┌───────────────────┐
│  repository.py    │  Existing spatial query layer (no change needed)
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  PostGIS          │
└───────────────────┘
```

### Interpretation Strategy

**Approach: LLM → Structured Intent → Predefined Functions**

Instead of letting the LLM generate raw SQL (risky: SQL injection, hallucinated column names,
wrong spatial functions), the LLM extracts a structured intent object:

```json
{
  "query_type": "within_radius",
  "lat": 20.700,
  "lon": -103.320,
  "radius_km": 5,
  "filters": { "start_date": "2026-03-01", "end_date": "2026-03-31" }
}
```

This intent maps to an existing, tested function in `repository.py`. The LLM never touches SQL.

**System prompt** includes:
- Table schema (column names, types)
- List of available query types and their parameters
- Few-shot examples of NL → intent JSON
- Hard constraint: respond only with valid JSON, no prose

### Trade-offs

| Dimension | LLM → Intent (chosen) | Raw SQL generation | RAG |
|-----------|----------------------|--------------------|-----|
| **Precision** | High (bounded function set) | Medium (hallucination risk) | Low for spatial |
| **Cost** | Low (small prompt) | Low | High (embedding + retrieval) |
| **Latency** | ~500ms LLM + <50ms query | ~500ms + query | ~1s+ |
| **Complexity** | Low | Medium | High |
| **Safety** | High (no SQL injection surface) | Low | High |

### Future Evolution

- **Provider independence**: abstract the LLM call behind an interface; swap Claude ↔ GPT-4o ↔ local Llama without changing the router
- **Fallback**: if intent confidence < threshold, route to a clarification prompt rather than executing
- **Caching**: cache identical NL queries (hash-keyed) to reduce LLM calls
- **Evaluation**: log (query, intent, result) triples and periodically evaluate intent accuracy

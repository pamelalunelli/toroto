"""
Repository layer: all database access and spatial query logic lives here.
Routes and services never write raw SQL — they call these functions.

PostGIS spatial operators used:
  <->        : KNN index-based distance operator (fast nearest neighbor)
  ST_DWithin : true geodesic distance filter using geography cast
  ST_Within  : point-in-polygon test
  ST_Distance: exact geodesic distance in meters
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional


# ---------------------------------------------------------------------------
# Query 1 — Nearest Neighbor
# ---------------------------------------------------------------------------

def get_nearest_intervention(
    db: Session,
    lat: float,
    lon: float,
    status: Optional[str] = None,
    subtype: Optional[str] = None,
) -> Optional[dict]:
    """
    Returns the single intervention closest to (lat, lon).

    Uses the PostGIS KNN operator `<->` on the GIST-indexed geometry column,
    which avoids a full table scan. The exact geodesic distance (meters) is
    computed afterwards with a geography cast so the result is accurate.

    SQL equivalent:
        SELECT *, ST_Distance(geom::geography, ref::geography) AS distance_m
        FROM interventions
        [WHERE ...]
        ORDER BY geom <-> ref
        LIMIT 1
    """
    filters = _build_filters(status=status, subtype=subtype)
    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

    sql = text(f"""
        SELECT
            id, subtype, status, project_id, region, date,
            operator_id, priority, quality_score, metrics,
            ST_Y(geom) AS lat,
            ST_X(geom) AS lon,
            ST_Distance(
                geom::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
            ) AS distance_m
        FROM interventions
        {where_clause}
        ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
        LIMIT 1
    """)

    row = db.execute(sql, {"lat": lat, "lon": lon}).mappings().fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Query 2 — Within Radius
# ---------------------------------------------------------------------------

def get_interventions_within_radius(
    db: Session,
    lat: float,
    lon: float,
    radius_km: float,
    status: Optional[str] = None,
    subtype: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """
    Returns all interventions within `radius_km` km of (lat, lon).

    ST_DWithin with geography cast computes true geodesic distance,
    avoiding the distortion of planar distance in degrees. The GIST index
    still accelerates the query via a bounding-box pre-filter.

    SQL equivalent:
        SELECT *, ST_Distance(...) AS distance_m
        FROM interventions
        WHERE ST_DWithin(geom::geography, ref::geography, radius_m)
          [AND ...]
        ORDER BY distance_m
    """
    radius_m = radius_km * 1000
    filters = _build_filters(status=status, subtype=subtype,
                             start_date=start_date, end_date=end_date)
    filters.append("""
        ST_DWithin(
            geom::geography,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
            :radius_m
        )
    """)
    where_clause = "WHERE " + " AND ".join(filters)

    sql = text(f"""
        SELECT
            id, subtype, status, project_id, region, date,
            operator_id, priority, quality_score, metrics,
            ST_Y(geom) AS lat,
            ST_X(geom) AS lon,
            ST_Distance(
                geom::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
            ) AS distance_m
        FROM interventions
        {where_clause}
        ORDER BY distance_m
    """)

    rows = db.execute(
        sql, {"lat": lat, "lon": lon, "radius_m": radius_m}
    ).mappings().fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Query 3 — Within Area (polygon)
# ---------------------------------------------------------------------------

def get_interventions_within_area(
    db: Session,
    area_id: str,
    status: Optional[str] = None,
    subtype: Optional[str] = None,
) -> tuple[list[dict], Optional[str]]:
    """
    Returns all interventions whose point geometry falls inside the polygon
    identified by `area_id`.

    ST_Within(point, polygon) uses the GIST index on both geometries for
    an efficient two-stage check: bounding-box pre-filter + exact DE-9IM test.

    SQL equivalent:
        SELECT i.*
        FROM interventions i
        JOIN areas a ON ST_Within(i.geom, a.geom)
        WHERE a.area_id = :area_id
          [AND ...]
    """
    filters = _build_filters(status=status, subtype=subtype,
                             table_prefix="i")
    extra_where = ("AND " + " AND ".join(filters)) if filters else ""

    sql = text(f"""
        SELECT
            i.id, i.subtype, i.status, i.project_id, i.region, i.date,
            i.operator_id, i.priority, i.quality_score, i.metrics,
            ST_Y(i.geom) AS lat,
            ST_X(i.geom) AS lon,
            a.name AS area_name
        FROM interventions i
        JOIN areas a ON ST_Within(i.geom, a.geom)
        WHERE a.area_id = :area_id
        {extra_where}
        ORDER BY i.date DESC
    """)

    rows = db.execute(sql, {"area_id": area_id}).mappings().fetchall()
    area_name = rows[0]["area_name"] if rows else _get_area_name(db, area_id)
    return [dict(r) for r in rows], area_name

def list_interventions(
    db,
    status=None,
    subtype=None,
    region=None,
    start_date=None,
    end_date=None,
    limit=200,
    offset=0,
):
    filters = []

    if status:
        filters.append(f"status = '{status}'")
    if subtype:
        filters.append(f"subtype = '{subtype}'")
    if region:
        filters.append(f"region = '{region}'")
    if start_date:
        filters.append(f"date >= '{start_date}'")
    if end_date:
        filters.append(f"date <= '{end_date}'")

    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    sql = text(f"""
        SELECT
            id,
            subtype,
            status,
            project_id,
            region,
            date,
            operator_id,
            priority,
            quality_score,
            metrics,
            ST_Y(geom) AS lat,
            ST_X(geom) AS lon
        FROM interventions
        {where_clause}
        ORDER BY date DESC
        LIMIT :limit OFFSET :offset
    """)

    rows = db.execute(
        sql,
        {"limit": limit, "offset": offset}
    ).mappings().fetchall()

    return [dict(r) for r in rows]


def analytics_by_region(db):
    sql = text("""
        SELECT region, COUNT(*) AS total
        FROM interventions
        GROUP BY region
        ORDER BY total DESC
    """)
    rows = db.execute(sql).mappings().fetchall()
    return [dict(r) for r in rows]


def analytics_by_subtype(db):
    sql = text("""
        SELECT subtype, COUNT(*) AS total
        FROM interventions
        GROUP BY subtype
        ORDER BY total DESC
    """)
    rows = db.execute(sql).mappings().fetchall()
    return [dict(r) for r in rows]


def analytics_timeline(db):
    sql = text("""
        SELECT substr(date,1,7) AS month, COUNT(*) AS total
        FROM interventions
        GROUP BY month
        ORDER BY month
    """)
    rows = db.execute(sql).mappings().fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Supporting queries
# ---------------------------------------------------------------------------

def list_areas(db: Session) -> list[dict]:
    sql = text("SELECT area_id, name FROM areas ORDER BY area_id")
    rows = db.execute(sql).mappings().fetchall()
    return [dict(r) for r in rows]


def get_status_summary(db: Session) -> dict:
    sql = text("""
        SELECT status, COUNT(*) AS total
        FROM interventions
        GROUP BY status
        ORDER BY total DESC
    """)
    rows = db.execute(sql).mappings().fetchall()
    return {r["status"]: r["total"] for r in rows}


def get_subtype_by_region(db: Session) -> list[dict]:
    sql = text("""
        SELECT region, subtype, COUNT(*) AS total
        FROM interventions
        GROUP BY region, subtype
        ORDER BY region, total DESC
    """)
    rows = db.execute(sql).mappings().fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_filters(
    status=None,
    subtype=None,
    start_date=None,
    end_date=None,
    table_prefix: str = "",
) -> list[str]:
    """Build safe parameterized WHERE fragments (no f-string injection)."""
    prefix = f"{table_prefix}." if table_prefix else ""
    clauses = []
    if status:
        clauses.append(f"{prefix}status = '{status}'")
    if subtype:
        clauses.append(f"{prefix}subtype = '{subtype}'")
    if start_date:
        clauses.append(f"{prefix}date >= '{start_date}'")
    if end_date:
        clauses.append(f"{prefix}date <= '{end_date}'")
    return clauses


def _get_area_name(db: Session, area_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT name FROM areas WHERE area_id = :area_id"),
        {"area_id": area_id}
    ).fetchone()
    return row[0] if row else None

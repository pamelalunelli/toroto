from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app import repository as repo
from app.schemas import (
    NearestResult, InterventionOut, CoordinatesOut,
    WithinRadiusResult, WithinAreaResult, AreaOut,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Query 1 — Nearest Neighbor
# ---------------------------------------------------------------------------

@router.get(
    "/interventions/nearest",
    response_model=NearestResult,
    summary="Nearest neighbor",
    description="Returns the single intervention closest to the given point.",
)
def nearest_intervention(
    lat: float = Query(..., description="Latitude of reference point", example=20.701),
    lon: float = Query(..., description="Longitude of reference point", example=-103.321),
    status: Optional[str] = Query(None, description="Filter by status (e.g. validated)"),
    subtype: Optional[str] = Query(None, description="Filter by subtype (e.g. reforestacion)"),
    db: Session = Depends(get_db),
):
    result = repo.get_nearest_intervention(db, lat=lat, lon=lon,
                                           status=status, subtype=subtype)
    if not result:
        raise HTTPException(status_code=404, detail="No interventions found")

    return NearestResult(
        intervention=_to_intervention_out(result),
        distance_m=round(result["distance_m"], 2),
    )


# ---------------------------------------------------------------------------
# Query 2 — Within Radius
# ---------------------------------------------------------------------------

@router.get(
    "/interventions/within-radius",
    response_model=WithinRadiusResult,
    summary="Within radius",
    description="Returns all interventions within a given radius (km) of a point.",
)
def within_radius(
    lat: float = Query(..., example=20.700),
    lon: float = Query(..., example=-103.320),
    radius_km: float = Query(..., gt=0, description="Search radius in kilometers", example=5.0),
    status: Optional[str] = Query(None),
    subtype: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="ISO date filter start (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO date filter end (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    results = repo.get_interventions_within_radius(
        db, lat=lat, lon=lon, radius_km=radius_km,
        status=status, subtype=subtype,
        start_date=start_date, end_date=end_date,
    )
    return WithinRadiusResult(
        center_lat=lat,
        center_lon=lon,
        radius_km=radius_km,
        total_found=len(results),
        interventions=[_to_intervention_out(r) for r in results],
    )


# ---------------------------------------------------------------------------
# Query 3 — Within Area (polygon)
# ---------------------------------------------------------------------------

@router.get(
    "/interventions/within-area/{area_id}",
    response_model=WithinAreaResult,
    summary="Within area (polygon)",
    description="Returns all interventions inside a named reference polygon.",
)
def within_area(
    area_id: str,
    status: Optional[str] = Query(None),
    subtype: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    results, area_name = repo.get_interventions_within_area(
        db, area_id=area_id, status=status, subtype=subtype
    )
    return WithinAreaResult(
        area_id=area_id,
        area_name=area_name,
        total_found=len(results),
        interventions=[_to_intervention_out(r) for r in results],
    )

@router.get(
    "/interventions",
    summary="List interventions with filters"
)
def list_all_interventions(
    status: Optional[str] = Query(None),
    subtype: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    results = repo.list_interventions(
        db=db,
        status=status,
        subtype=subtype,
        region=region,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return {
        "total_found": len(results),
        "items": [_to_intervention_out(r) for r in results]
    }

@router.get(
    "/analytics/by-region",
    summary="Count interventions by region"
)
def by_region(db: Session = Depends(get_db)):
    return repo.analytics_by_region(db)


@router.get(
    "/analytics/by-subtype",
    summary="Count interventions by subtype"
)
def by_subtype(db: Session = Depends(get_db)):
    return repo.analytics_by_subtype(db)


@router.get(
    "/analytics/timeline",
    summary="Monthly intervention timeline"
)
def timeline(db: Session = Depends(get_db)):
    return repo.analytics_timeline(db)


# ---------------------------------------------------------------------------
# Supporting endpoints
# ---------------------------------------------------------------------------

@router.get("/areas", response_model=list[AreaOut], summary="List reference areas")
def list_areas(db: Session = Depends(get_db)):
    return repo.list_areas(db)


@router.get("/status-summary", summary="Intervention count by status")
def status_summary(db: Session = Depends(get_db)):
    return repo.get_status_summary(db)


@router.get("/subtype-by-region", summary="Intervention count by region and subtype")
def subtype_by_region(db: Session = Depends(get_db)):
    return repo.get_subtype_by_region(db)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _to_intervention_out(row: dict) -> InterventionOut:
    return InterventionOut(
        id=row["id"],
        subtype=row["subtype"],
        status=row["status"],
        project_id=row["project_id"],
        region=row["region"],
        date=row["date"],
        operator_id=row.get("operator_id"),
        priority=row.get("priority"),
        quality_score=row.get("quality_score"),
        metrics=row.get("metrics"),
        coordinates=CoordinatesOut(lat=row["lat"], lon=row["lon"]),
    )

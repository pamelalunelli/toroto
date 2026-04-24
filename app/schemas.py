from pydantic import BaseModel
from typing import Any, Optional


class CoordinatesOut(BaseModel):
    lat: float
    lon: float


class InterventionOut(BaseModel):
    id: str
    subtype: str
    status: str
    project_id: str
    region: str
    coordinates: CoordinatesOut
    date: str
    operator_id: Optional[str] = None
    priority: Optional[str] = None
    quality_score: Optional[float] = None
    metrics: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class NearestResult(BaseModel):
    intervention: InterventionOut
    distance_m: float


class WithinRadiusResult(BaseModel):
    center_lat: float
    center_lon: float
    radius_km: float
    total_found: int
    interventions: list[InterventionOut]


class WithinAreaResult(BaseModel):
    area_id: str
    area_name: Optional[str]
    total_found: int
    interventions: list[InterventionOut]


class AreaOut(BaseModel):
    area_id: str
    name: str

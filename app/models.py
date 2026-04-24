from sqlalchemy import Column, String, Float, DateTime, JSON
from geoalchemy2 import Geometry
from app.database import Base


class Intervention(Base):
    """
    Stores each geospatial intervention as a PostGIS POINT (SRID 4326 = WGS84).
    GIST index on `geom` enables fast spatial operators like <-> and ST_DWithin.
    """
    __tablename__ = "interventions"

    id = Column(String, primary_key=True)
    subtype = Column(String, index=True)
    status = Column(String, index=True)
    project_id = Column(String, index=True)
    region = Column(String, index=True)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    date = Column(String)
    intervention_timestamp = Column(DateTime)
    operator_id = Column(String)
    priority = Column(String)
    source = Column(String)
    quality_score = Column(Float)
    extra_metadata = Column(JSON)
    metrics = Column(JSON)


class Area(Base):
    """
    Reference polygons for within-area queries.
    Also indexed with GIST for ST_Contains / ST_Within operations.
    """
    __tablename__ = "areas"

    area_id = Column(String, primary_key=True)
    name = Column(String)
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False)

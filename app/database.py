from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables and spatial indexes if they don't exist."""
    with engine.connect() as conn:
        # Enable PostGIS extension
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()

    # Import here to avoid circular imports
    from app.models import Base as ModelBase  # noqa: F401
    ModelBase.metadata.create_all(bind=engine)

    # Create GIST spatial indexes for fast spatial queries
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_interventions_geom
            ON interventions USING GIST (geom)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_areas_geom
            ON areas USING GIST (geom)
        """))
        conn.commit()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://toroto:toroto@localhost:5432/geospatial"
    groq_api_key: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()

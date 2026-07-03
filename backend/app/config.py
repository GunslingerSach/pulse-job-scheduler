from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://scheduler:scheduler@localhost:5432/job_scheduler"
    jwt_secret: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    worker_poll_interval_seconds: float = 1.0
    heartbeat_interval_seconds: float = 5.0
    worker_offline_threshold_seconds: int = 20
    default_job_timeout_seconds: int = 300

    class Config:
        env_file = ".env"


settings = Settings()

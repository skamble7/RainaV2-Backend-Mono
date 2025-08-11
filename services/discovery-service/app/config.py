# app/config.py
from pydantic_settings import BaseSettings
from pydantic import field_validator

class Settings(BaseSettings):
    # Mongo
    MONGO_URI: str
    MONGO_DB: str = "RainaV2"

    # Downstream services
    CAPABILITY_REGISTRY_URL: str
    ARTIFACT_SERVICE_URL: str

    # Pack location for playbooks (defaults; per-request override via options)
    PACK_KEY: str = "svc-micro"
    PACK_VERSION: str = "v1"

    # Messaging
    RABBITMQ_URI: str
    RABBITMQ_EXCHANGE: str = "raina.events"

    # LLM Config
    MODEL_ID: str = "openai:gpt-4o-mini"
    OPENAI_API_KEY: str | None = None

    # Service Metadata
    SERVICE_NAME: str = "discovery-service"
    PORT: int = 8013
    ENV: str = "local"

    # Optional
    REQUEST_TIMEOUT_S: int = 60

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @field_validator("MONGO_URI")
    @classmethod
    def _no_placeholder_uri(cls, v: str) -> str:
        if "://" not in v:
            raise ValueError("MONGO_URI must be a valid connection string")
        return v

settings = Settings()  # type: ignore

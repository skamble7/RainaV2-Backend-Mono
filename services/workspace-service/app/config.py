# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Mongo
    MONGO_URI: str
    MONGO_DB: str = "RainaV2"

    # Messaging (topic exchange)
    RABBITMQ_URI: str
    RABBITMQ_EXCHANGE: str = "raina.events"  # keep existing exchange; RK org segment changes

    # Events: org/tenant segment for versioned routing keys
    # Final RK shape => <EVENTS_ORG>.workspace.<event>.v1
    # We default to "platform" for inter-platform events.
    EVENTS_ORG: str = "platform"

    # Platform detection
    # Header to read the caller platform from; if missing, we fall back to DEFAULT_ORIGIN_PLATFORM.
    PLATFORM_HEADER: str = "x-platform-id"
    DEFAULT_ORIGIN_PLATFORM: str = "raina"  # override to "renova" in Renova callers if desired

    # Service metadata
    SERVICE_NAME: str = "workspace-service"
    PORT: int = 8010
    ENV: str = "local"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

settings = Settings()  # type: ignore

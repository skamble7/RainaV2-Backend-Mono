# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Mongo
    MONGO_URI: str                 # MongoDB Atlas connection string
    MONGO_DB: str = "RainaV2"

    # Messaging (topic exchange)
    RABBITMQ_URI: str
    RABBITMQ_EXCHANGE: str = "raina.events"

    # Events: org/tenant segment for versioned routing keys
    # Final RK shape => <EVENTS_ORG>.workspace.<event>.v1
    EVENTS_ORG: str = "raina"

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

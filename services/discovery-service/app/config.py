from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Downstream services
    CAPABILITY_REGISTRY_URL: str
    # Pack location for playbooks:
    PACK_KEY: str = "svc-micro"
    PACK_VERSION: str = "v1"
    
    ARTIFACT_SERVICE_URL: str

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

settings = Settings()  # type: ignore

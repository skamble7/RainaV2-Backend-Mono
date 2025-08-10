from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGO_URI: str  # MongoDB Atlas connection string
    MONGO_DB: str = "RainaV2"
    RABBITMQ_URI: str
    RABBITMQ_EXCHANGE: str = "raina.events"
    SERVICE_NAME: str = "workspace-service"
    PORT: int = 8010
    ENV: str = "local"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

settings = Settings()  # type: ignore
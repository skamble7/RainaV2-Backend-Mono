# app/config.py
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict  # <-- new

class Settings(BaseSettings):
    SERVICE_NAME: str = "guidance-service"
    SERVICE_PORT: int = 8014

    # External services
    ARTIFACT_SERVICE_URL: str = "http://artifact-service:8011"
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/%2F"

    # LLM config
    LLM_PROVIDER: str = "openai"
    LLM_MODEL_ID: str = "gpt-4o-mini"
    LLM_TEMP: float = 0.2
    LLM_MAX_TOKENS: int = 4000

    # API keys (optional per provider)
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_DEPLOYMENT: Optional[str] = None

    # Generation options
    DEFAULT_SECTIONS: List[str] = [
        "overview","service_catalog","apis","events","nfrs",
        "topology","observability","ops_runbooks","adrs"
    ]

    # Filesystem
    OUTPUT_DIR: str = "/output"

    # pydantic v2 settings config (replaces v1 'class Config')
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

settings = Settings()

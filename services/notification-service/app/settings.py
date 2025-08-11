from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SERVICE_NAME: str = "notification-service"
    ENV: str = "dev"

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"
    RABBITMQ_EXCHANGE: str = "raina.events"
    RABBITMQ_EXCHANGE_TYPE: str = "topic"
    RABBITMQ_QUEUE: str = "notification-service.v1"
    RABBITMQ_BINDINGS: list[str] = [
        "*.workspace.*.v1",
        "*.artifact.*.v1",
        "*.discovery.*.v1",
        "*.guidance.*.v1",
        "*.capability.*.v1",
        "*.notification.*.v1",
        "*.audit.*.v1",
        "*.error.*.v1",
    ]

    # WebSocket
    WS_PATH: str = "/ws"  # connect to /ws?tenant_id=...&workspace_id=...
    WS_ALLOW_ORIGINS: list[str] = ["*"]  # tighten in prod

    # Replay buffer
    BUFFER_SIZE_PER_WORKSPACE: int = 200

    class Config:
        env_file = ".env"

settings = Settings()

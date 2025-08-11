# services/artifact-service/app/config.py
from pydantic import BaseModel
import os

class Settings(BaseModel):
    app_name: str = "RAINA Artifact Service"
    host: str = "0.0.0.0"
    port: int = 8011

    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "RainaV2")

    rabbitmq_uri: str = os.getenv("RABBITMQ_URI", "amqp://guest:guest@localhost:5672/")
    rabbitmq_exchange: str = os.getenv("RABBITMQ_EXCHANGE", "raina.events")

    # Event routing keys + queue
    workspace_created_rk: str = os.getenv("WORKSPACE_CREATED_RK", "workspace.created")
    workspace_updated_rk: str = os.getenv("WORKSPACE_UPDATED_RK", "workspace.updated")      # ← add
    workspace_deleted_rk: str = os.getenv("WORKSPACE_DELETED_RK", "workspace.deleted")      # ← add
    consumer_queue_ws_created: str = os.getenv(
        "CONSUMER_QUEUE_WS_CREATED", "artifact-service.workspace.created"
    )

settings = Settings()

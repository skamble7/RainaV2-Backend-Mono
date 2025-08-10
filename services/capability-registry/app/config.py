from pydantic import BaseModel
import os

class Settings(BaseModel):
    app_name: str = "RAINA Capability Registry"
    host: str = "0.0.0.0"
    port: int = 8012
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "RainaV2")
    rabbitmq_uri: str = os.getenv("RABBITMQ_URI", "amqp://guest:guest@localhost:5672/")
    rabbitmq_exchange: str = os.getenv("RABBITMQ_EXCHANGE", "raina.events")

settings = Settings()

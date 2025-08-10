import pika, json
from app.config import settings

def publish_event(event_type: str, workspace_id: str, payload: dict):
    params = pika.URLParameters(settings.RABBITMQ_URI)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange=settings.RABBITMQ_EXCHANGE, exchange_type="topic", durable=True)
    msg = json.dumps({"type": event_type, "workspace_id": workspace_id, "payload": payload}, default=str)
    ch.basic_publish(exchange=settings.RABBITMQ_EXCHANGE, routing_key=event_type, body=msg)
    conn.close()

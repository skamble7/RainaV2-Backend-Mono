import orjson, pika
from ..config import settings
_channel = None; _conn = None
def _ensure():
    global _channel, _conn
    if _channel and _channel.is_open: return
    _conn = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_uri))
    _channel = _conn.channel()
    _channel.exchange_declare(exchange=settings.rabbitmq_exchange, exchange_type="topic", durable=True)
def publish_event(routing_key: str, payload: dict):
    _ensure()
    _channel.basic_publish(
        exchange=settings.rabbitmq_exchange,
        routing_key=routing_key,
        body=orjson.dumps(payload),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )

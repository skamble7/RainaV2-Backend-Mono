# app/events/rabbit.py
import orjson
import pika
from ..config import settings

_channel = None
_connection = None

def _ensure_conn():
    global _channel, _connection
    if _channel and _channel.is_open:
        return
    params = pika.URLParameters(settings.rabbitmq_uri)
    _connection = pika.BlockingConnection(params)
    _channel = _connection.channel()
    _channel.exchange_declare(exchange=settings.rabbitmq_exchange, exchange_type="topic", durable=True)

def publish_event(routing_key: str, payload: dict):
    _ensure_conn()
    _channel.basic_publish(
        exchange=settings.rabbitmq_exchange,
        routing_key=routing_key,
        body=orjson.dumps(payload),  # <— serialize datetimes correctly
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )

# app/events/rabbit.py
import orjson
from aio_pika import connect_robust, ExchangeType, Message
from app.config import settings

_connection = None
_channel = None
_exchange = None


async def _ensure_exchange():
    """Ensure RabbitMQ connection, channel, and exchange are ready."""
    global _connection, _channel, _exchange
    if _exchange:
        return _exchange
    _connection = await connect_robust(settings.RABBITMQ_URI)
    _channel = await _connection.channel()
    _exchange = await _channel.declare_exchange(
        settings.RABBITMQ_EXCHANGE,
        ExchangeType.TOPIC,
        durable=True
    )
    return _exchange


async def publish_event(routing_key: str, payload: dict):
    """Publish a raw event with the given routing key."""
    ex = await _ensure_exchange()
    body = orjson.dumps(payload)
    msg = Message(body, content_type="application/json", delivery_mode=2)
    await ex.publish(msg, routing_key=routing_key)


async def publish_event_v1(event: str, payload: dict, org: str | None = None):
    """
    Publish an event using the canonical v1 routing key format:
    {org}.workspace.{event}.v1
    Example: platform.workspace.created.v1
    """
    ex = await _ensure_exchange()
    routing_key = f"{org or getattr(settings, 'EVENTS_ORG', 'platform')}.workspace.{event}.v1"
    body = orjson.dumps(payload)
    msg = Message(body, content_type="application/json", delivery_mode=2)
    await ex.publish(msg, routing_key=routing_key)


async def close():
    """Close the RabbitMQ connection if open."""
    global _connection
    if _connection:
        await _connection.close()
        _connection = None

import orjson
from aio_pika import connect_robust, ExchangeType, Message
from app.config import settings

_connection = None
_channel = None
_exchange = None

async def _ensure():
    global _connection, _channel, _exchange
    if _exchange:
        return _exchange
    _connection = await connect_robust(settings.RABBITMQ_URI)
    _channel = await _connection.channel()
    _exchange = await _channel.declare_exchange(
        settings.RABBITMQ_EXCHANGE, ExchangeType.TOPIC, durable=True
    )
    return _exchange

async def publish_event(routing_key: str, payload: dict):
    ex = await _ensure()
    # orjson serializes datetimes (RFC3339) and returns bytes
    body = orjson.dumps(payload)
    msg = Message(body, content_type="application/json")
    await ex.publish(msg, routing_key=routing_key)

async def close():
    global _connection
    if _connection:
        await _connection.close()
        _connection = None

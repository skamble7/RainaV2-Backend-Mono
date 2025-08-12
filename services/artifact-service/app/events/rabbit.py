# app/events/rabbit.py
import logging
import orjson
import pika
import threading
import time
from typing import Optional, Dict

from ..config import settings

# Optional: pull correlation/request IDs from middleware if present
try:
    from ..middleware.correlation import request_id_var, correlation_id_var  # type: ignore
except Exception:  # pragma: no cover
    request_id_var = correlation_id_var = None  # type: ignore

logger = logging.getLogger("app.events.rabbit")

_lock = threading.Lock()
_connection: Optional[pika.BlockingConnection] = None
_channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None

def _connect():
    global _connection, _channel
    params = pika.URLParameters(settings.rabbitmq_uri)
    _connection = pika.BlockingConnection(params)
    _channel = _connection.channel()
    _channel.exchange_declare(
        exchange=settings.rabbitmq_exchange,
        exchange_type="topic",
        durable=True,
    )
    logger.info("Rabbit: connected and exchange declared",
                extra={"exchange": settings.rabbitmq_exchange})

def _ensure_conn():
    global _connection, _channel
    if _channel and _channel.is_open:
        return
    with _lock:
        if _channel and _channel.is_open:
            return
        _connect()

def _close_dead():
    global _connection, _channel
    try:
        if _channel and _channel.is_open:
            _channel.close()
    except Exception:
        pass
    try:
        if _connection and _connection.is_open:
            _connection.close()
    except Exception:
        pass
    _channel = None
    _connection = None

def publish_event(routing_key: str, payload: dict, headers: Optional[Dict[str, str]] = None) -> bool:
    """
    Returns True on publish success, False if publishing failed (caller should not crash).
    Retries once after reconnect.
    """
    # Attach correlation data if available
    hdrs = dict(headers or {})
    try:
        if request_id_var:
            rid = request_id_var.get()
            if rid:
                hdrs.setdefault("x-request-id", rid)
        if correlation_id_var:
            cid = correlation_id_var.get()
            if cid:
                hdrs.setdefault("x-correlation-id", cid)
    except Exception:
        pass

    body = orjson.dumps(payload)

    for attempt in (1, 2):
        try:
            _ensure_conn()
            assert _channel is not None
            _channel.basic_publish(
                exchange=settings.rabbitmq_exchange,
                routing_key=routing_key,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # persistent
                    headers=hdrs or None,
                ),
                mandatory=False,
            )
            logger.info("Rabbit: event published",
                        extra={"routing_key": routing_key, "attempt": attempt})
            return True
        except Exception as e:
            logger.exception("Rabbit publish failed; %s", type(e).__name__,
                             extra={"routing_key": routing_key, "attempt": attempt})
            _close_dead()
            time.sleep(0.1)  # small backoff and try once more
    return False

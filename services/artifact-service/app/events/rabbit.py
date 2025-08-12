# app/events/rabbit.py
from __future__ import annotations

import logging
import orjson
import pika
import threading
from typing import Optional
from ..config import settings

logger = logging.getLogger(__name__)

# Globals guarded by a lock for basic thread safety
_connection: Optional[pika.BlockingConnection] = None
_channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None
_lock = threading.RLock()


def _connect() -> None:
    """
    (Re)establish a BlockingConnection + channel and declare the exchange.
    """
    global _connection, _channel
    params = pika.URLParameters(settings.rabbitmq_uri)

    # Optional resilience tweaks (safe to set if supported by your pika version)
    try:
        # Heartbeats help detect dead peers; tune as needed
        params.heartbeat = getattr(params, "heartbeat", 30) or 30
        # Avoid hanging on blocked connections
        params.blocked_connection_timeout = getattr(params, "blocked_connection_timeout", 10) or 10
        # A few connection attempts with small delay
        params.connection_attempts = getattr(params, "connection_attempts", 3) or 3
        params.retry_delay = getattr(params, "retry_delay", 2) or 2
        # Reasonable socket timeout
        params.socket_timeout = getattr(params, "socket_timeout", 5) or 5
    except Exception:
        # If any of these attrs don't exist in your pika version, just continue
        pass

    _connection = pika.BlockingConnection(params)
    _channel = _connection.channel()

    # Ensure topic exchange exists and is durable
    _channel.exchange_declare(
        exchange=settings.rabbitmq_exchange,
        exchange_type="topic",
        durable=True,
    )


def _ensure_channel() -> None:
    """
    Ensure we have an open channel; reconnect if needed.
    """
    global _connection, _channel
    if _channel and _channel.is_open:
        return
    if _connection and _connection.is_open:
        try:
            _channel = _connection.channel()
            if _channel and _channel.is_open:
                # Re-declare in case broker restarted
                _channel.exchange_declare(
                    exchange=settings.rabbitmq_exchange,
                    exchange_type="topic",
                    durable=True,
                )
                return
        except Exception:
            # Fall through to full reconnect
            pass
    # Full reconnect
    _connect()


def _reset() -> None:
    """
    Drop references so next publish attempts a fresh connect.
    """
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


def publish_event(routing_key: str, payload: dict) -> bool:
    """
    Publish a JSON event to the configured topic exchange.
    Returns True on success, False on failure.
    Never raises—safe to call on your hot path.
    """
    body = orjson.dumps(payload)

    with _lock:
        # Try once, then reset/reconnect and try once more
        for attempt in (1, 2):
            try:
                _ensure_channel()
                assert _channel is not None  # for type checkers
                _channel.basic_publish(
                    exchange=settings.rabbitmq_exchange,
                    routing_key=routing_key,
                    body=body,
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=2,  # persistent
                    ),
                )
                return True
            except Exception as e:
                # Log and try a clean reconnect on the next attempt
                logger.warning(
                    "Rabbit publish attempt %d failed for key '%s': %s",
                    attempt, routing_key, repr(e)
                )
                _reset()

        # If we got here, both attempts failed. Log and move on.
        logger.exception(
            "Failed to publish event after retries for key '%s'. Continuing without event.",
            routing_key
        )
        return False

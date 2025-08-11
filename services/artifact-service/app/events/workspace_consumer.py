# app/events/workspace_consumer.py
from __future__ import annotations

import asyncio
import json
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
import aio_pika

from ..config import settings
from ..dal import artifact_dal as dal
from ..models.artifact import WorkspaceSnapshot

log = logging.getLogger(__name__)


async def _handle_message(db: AsyncIOMotorDatabase, body: bytes) -> None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as e:
        log.exception("Invalid JSON on workspace.created: %s", e)
        return

    # Accept flat or wrapped payload
    try:
        ws = WorkspaceSnapshot.model_validate(payload)
    except Exception:
        if "workspace" in payload:
            ws = WorkspaceSnapshot.model_validate(payload["workspace"])
        else:
            log.error("workspace.created payload missing workspace fields: %s", payload)
            return

    ws_id = ws.id

    # Idempotent parent creation
    if await dal.get_parent_doc(db, ws_id):
        log.info("WorkspaceArtifactsDoc already exists for workspace_id=%s", ws_id)
        return

    created = await dal.create_parent_doc(db, ws)
    log.info("Created WorkspaceArtifactsDoc: workspace_id=%s, doc_id=%s", ws_id, created.id)


async def run_workspace_created_consumer(db: AsyncIOMotorDatabase, shutdown_event: asyncio.Event) -> None:
    """
    Long-running consumer. Reconnects on failure. Stops when shutdown_event is set.
    """
    while not shutdown_event.is_set():
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_uri)
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=1)

                exchange = await channel.declare_exchange(
                    settings.rabbitmq_exchange, aio_pika.ExchangeType.TOPIC, durable=True
                )

                queue = await channel.declare_queue(
                    settings.consumer_queue_ws_created, durable=True
                )
                await queue.bind(exchange, routing_key=settings.workspace_created_rk)

                log.info(
                    "Consuming queue=%s exchange=%s rk=%s",
                    settings.consumer_queue_ws_created,
                    settings.rabbitmq_exchange,
                    settings.workspace_created_rk,
                )

                async with queue.iterator() as q:
                    async for message in q:
                        if shutdown_event.is_set():
                            break
                        async with message.process(requeue=False):
                            await _handle_message(db, message.body)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.exception("workspace.created consumer error; retrying in 3s: %s", e)
            await asyncio.sleep(3.0)

    log.info("workspace.created consumer stopped")

# add small helpers
async def _normalize_payload(payload: dict) -> dict:
    data = payload.get("workspace", payload)
    if "_id" not in data and "id" in data:
      data = {**data, "_id": data["id"]}
    return data

async def _on_created(db, payload: dict):
    data = await _normalize_payload(payload)
    ws = WorkspaceSnapshot.model_validate(data)
    if await dal.get_parent_doc(db, ws.id):
        log.info("Parent already exists for workspace_id=%s", ws.id)
        return
    created = await dal.create_parent_doc(db, ws)
    log.info("Created WorkspaceArtifactsDoc: workspace_id=%s, doc_id=%s", ws.id, created.id)

async def _on_updated(db, payload: dict):
    data = await _normalize_payload(payload)
    ws = WorkspaceSnapshot.model_validate(data)
    await dal.refresh_workspace_snapshot(db, ws)
    log.info("Refreshed workspace snapshot for workspace_id=%s", ws.id)

# app/events/workspace_consumer.py

async def _on_deleted(db, payload: dict):
    # accept flat or wrapped payload
    data = payload.get("workspace", payload)
    wid = data.get("_id") or data.get("id")
    if not wid:
        log.error("workspace.deleted payload missing id/_id: %s", payload)
        return

    ok = await dal.delete_parent_doc(db, wid)
    log.info("Deleted parent doc for workspace_id=%s (ok=%s)", wid, ok)


async def run_workspace_created_consumer(db: AsyncIOMotorDatabase, shutdown_event: asyncio.Event) -> None:
    while not shutdown_event.is_set():
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_uri)
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=1)

                exchange = await channel.declare_exchange(
                    settings.rabbitmq_exchange, aio_pika.ExchangeType.TOPIC, durable=True
                )

                queue = await channel.declare_queue(
                    settings.consumer_queue_ws_created, durable=True
                )
                # Bind to created/updated/deleted
                await queue.bind(exchange, routing_key=settings.workspace_created_rk)
                await queue.bind(exchange, routing_key=getattr(settings, "workspace_updated_rk", "workspace.updated"))
                await queue.bind(exchange, routing_key=getattr(settings, "workspace_deleted_rk", "workspace.deleted"))

                log.info(
                    "Consuming queue=%s exchange=%s rk=[%s, %s, %s]",
                    settings.consumer_queue_ws_created,
                    settings.rabbitmq_exchange,
                    settings.workspace_created_rk,
                    getattr(settings, "workspace_updated_rk", "workspace.updated"),
                    getattr(settings, "workspace_deleted_rk", "workspace.deleted"),
                )

                async with queue.iterator() as q:
                    async for message in q:
                        if shutdown_event.is_set():
                            break
                        async with message.process(requeue=False):
                            rk = message.routing_key
                            try:
                                payload = json.loads(message.body.decode("utf-8"))
                            except Exception as e:
                                log.exception("Invalid JSON: %s", e)
                                continue

                            if rk == settings.workspace_created_rk:
                                await _on_created(db, payload)
                            elif rk == getattr(settings, "workspace_updated_rk", "workspace.updated"):
                                await _on_updated(db, payload)
                            elif rk == getattr(settings, "workspace_deleted_rk", "workspace.deleted"):
                                await _on_deleted(db, payload)
                            else:
                                log.warning("Unhandled routing key: %s", rk)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.exception("workspace consumer error; retrying in 3s: %s", e)
            await asyncio.sleep(3.0)

    log.info("workspace consumer stopped")

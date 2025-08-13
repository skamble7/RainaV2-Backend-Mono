# libs/raina_common/events.py
from __future__ import annotations
from enum import Enum

# Canonical exchange for all Raina services
EXCHANGE = "raina.events"

class Service(str, Enum):
    WORKSPACE = "workspace"
    ARTIFACT = "artifact"
    DISCOVERY = "discovery"
    GUIDANCE = "guidance"
    CAPABILITY = "capability"
    NOTIFICATION = "notification"
    AUDIT = "audit"
    ERROR = "error"

class Version(str, Enum):
    V1 = "v1"

def rk(org: str, service: Service | str, event: str, version: str = Version.V1.value) -> str:
    """
    Build the canonical versioned routing key:
        <org>.<service>.<event>.<version>

    Examples:
        rk("acme", Service.ARTIFACT, "created") -> "acme.artifact.created.v1"
    """
    svc = service.value if isinstance(service, Service) else str(service)
    return f"{org}.{svc}.{event}.{version}"

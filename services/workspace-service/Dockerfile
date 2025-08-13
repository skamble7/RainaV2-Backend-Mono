# services/workspace-service/Dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# TLS certs for Mongo Atlas + uv installer
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir uv

# 1) Install shared libs (editable) — copy project root + package dir
COPY libs/pyproject.toml /tmp/libs/pyproject.toml
COPY libs /tmp/libs/libs
RUN pip install --no-cache-dir -e /tmp/libs

# (optional) sanity check
RUN python - <<'PY'
import importlib
m = importlib.import_module("libs.raina_common.events")
print("OK:", m.__file__)
PY

# ----------------------------------
# 2) Copy service code and install
# ----------------------------------
COPY services/workspace-service/pyproject.toml /app/pyproject.toml
COPY services/workspace-service/app /app/app
# Install the service (regular, not dev extras)
RUN uv pip install --system /app

EXPOSE 8010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]

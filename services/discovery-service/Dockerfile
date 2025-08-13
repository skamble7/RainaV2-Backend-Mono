# services/discovery-service/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Base tools (uv + certs)
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
# 2) Copy service code + install
#    (install after code is present so pyproject can be resolved)
# ----------------------------------
COPY services/discovery-service/pyproject.toml /app/pyproject.toml
COPY services/discovery-service/app /app/app
RUN uv pip install --system /app

# ----------------------------------
# 3) Runtime
# ----------------------------------
EXPOSE 8013
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8013"]

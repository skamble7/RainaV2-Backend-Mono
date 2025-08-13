# services/guidance-service/Dockerfile
FROM python:3.11-slim

# ---- WeasyPrint system deps (PDF rendering) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libffi8 libcairo2 libjpeg62-turbo \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

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
# 2) Install guidance service
# ----------------------------------
COPY services/guidance-service/pyproject.toml /app/pyproject.toml
COPY services/guidance-service/app /app/app
RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir /app

# Output directory (mounted via compose)
RUN mkdir -p /output

EXPOSE 8014
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8014","--log-level","info"]

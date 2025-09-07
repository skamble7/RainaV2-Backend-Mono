# services/guidance-service/Dockerfile
FROM public.ecr.aws/docker/library/python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG DRAWIO_VER=24.5.3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/output \
    DRAWIO_DISABLE_UPDATE=1 \
    DRAWIO_NO_ANALYTICS=true \
    LIBGL_ALWAYS_SOFTWARE=1 \
    ELECTRON_DISABLE_SECURITY_WARNINGS=1 \
    XDG_RUNTIME_DIR=/tmp/runtime \
    DBUS_SESSION_BUS_ADDRESS=/dev/null

WORKDIR /app

# Ensure apt sources + update
RUN set -eux; \
  if [ ! -f /etc/apt/sources.list ]; then \
    echo "deb https://deb.debian.org/debian bookworm main" > /etc/apt/sources.list; \
    echo "deb https://security.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list; \
    echo "deb https://deb.debian.org/debian bookworm-updates main" >> /etc/apt/sources.list; \
  fi; \
  apt-get update -o Acquire::Retries=5

# Runtime deps for WeasyPrint + Electron draw.io
RUN set -eux; \
  apt-get install -y --no-install-recommends \
    ca-certificates curl wget jq \
    libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libffi8 libjpeg62-turbo \
    libasound2 libatk-bridge2.0-0 libatspi2.0-0 libcups2 libgtk-3-0 \
    libnss3 libnspr4 libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libxtst6 libxss1 libxkbcommon0 libdrm2 libgbm1 libxshmfence1 \
    libxrender1 fonts-liberation libvulkan1 \
    xvfb xauth \
  && rm -rf /var/lib/apt/lists/*

# Install draw.io Desktop (pinned)
RUN set -eux; \
  arch="$(dpkg --print-architecture)"; \
  case "$arch" in \
    amd64) pkg="drawio-amd64-${DRAWIO_VER}.deb" ;; \
    arm64) pkg="drawio-arm64-${DRAWIO_VER}.deb" ;; \
    *) echo "Unsupported arch: $arch" >&2; exit 1 ;; \
  esac; \
  url="https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_VER}/${pkg}"; \
  echo "Downloading $url"; \
  curl -fL --retry 5 --retry-delay 2 -o /tmp/drawio.deb "$url"; \
  apt-get update -o Acquire::Retries=5; \
  apt-get install -y --no-install-recommends /tmp/drawio.deb; \
  rm -rf /var/lib/apt/lists/* /tmp/drawio.deb

# Runtime dirs for Electron/Xvfb
RUN mkdir -p /tmp/runtime && chmod 777 /tmp/runtime
RUN command -v drawio || command -v draw.io

# ---- Install shared libs (editable) ----
COPY libs/pyproject.toml /tmp/libs/pyproject.toml
COPY libs /tmp/libs/libs
RUN pip install --no-cache-dir -e /tmp/libs

# quick import check
RUN python - <<'PY'
import importlib
m = importlib.import_module("libs.raina_common.events")
print("OK:", m.__file__)
PY

# ---- Install guidance service ----
COPY services/guidance-service/pyproject.toml /app/pyproject.toml
COPY services/guidance-service/app /app/app
RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir /app

RUN mkdir -p /output

EXPOSE 8014
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8014","--log-level","info"]

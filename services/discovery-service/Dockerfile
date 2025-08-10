FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv pip install --system -e .
COPY app ./app
EXPOSE 8013
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8013"]

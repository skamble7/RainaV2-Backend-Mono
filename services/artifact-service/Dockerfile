FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir uvicorn fastapi pydantic motor orjson jsonpatch pika httpx pytest pytest-asyncio
COPY app /app/app
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011"]

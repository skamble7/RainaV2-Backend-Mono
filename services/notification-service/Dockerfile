FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

COPY app /app/app

EXPOSE 8013
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8013"]

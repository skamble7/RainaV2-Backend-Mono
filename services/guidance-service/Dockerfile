FROM python:3.11-slim

# WeasyPrint deps
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libffi8 libcairo2 libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir -e .

# output outside app (you already mounted /output)
RUN mkdir -p /output

EXPOSE 8014
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8014","--log-level","info"]

FROM python:3.12-slim
WORKDIR /app

# Copy only dependency files first for better build caching
COPY pyproject.toml /app/

# Install pip-tools to handle pyproject.toml
RUN pip install --no-cache-dir pip-tools

# Compile and install dependencies
RUN pip install --no-cache-dir .

# Now copy the actual application code
COPY app /app/app

ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011"]

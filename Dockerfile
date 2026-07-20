# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 waitwatch && mkdir -p /app/data /app/reports \
    && chown -R waitwatch:waitwatch /app
USER waitwatch
ENTRYPOINT ["dtf-waitwatch"]
CMD ["run", "--config", "/app/config.toml"]
FROM mcr.microsoft.com/playwright/python:v1.54.0-noble AS browser
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[browser]"
RUN useradd --create-home --uid 10001 waitwatch 2>/dev/null || true \
    && mkdir -p /app/data /app/reports && chown -R waitwatch:waitwatch /app
USER waitwatch
ENTRYPOINT ["dtf-waitwatch"]
CMD ["run", "--config", "/app/config.toml"]

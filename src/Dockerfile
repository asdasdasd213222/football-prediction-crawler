FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir \
    'celery>=5.4,<6' \
    'pydantic>=2.8,<3' \
    'PyYAML>=6.0,<7' \
    'redis>=5.0,<6' \
    'SQLAlchemy>=2.0,<3'
COPY multisite_crawler ./multisite_crawler
RUN useradd --create-home --uid 10001 worker
USER worker

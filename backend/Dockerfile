# Build context: the repo root (the API reads database/migrations at startup).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/backend

COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

COPY database/migrations /srv/database/migrations
COPY backend/app ./app
COPY backend/tests ./tests

EXPOSE 8010
# First start applies the migrations and seeds the demo world (~30 s) before serving.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]

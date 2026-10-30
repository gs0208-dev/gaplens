FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Third-party packages come from the hashed lock file, in a layer that is cached until the lock
# changes. Our own code is not pip-installed: uvicorn and alembic run from /srv, so the build
# fetches nothing outside the lock.
COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN useradd --system --uid 10001 --no-create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.15-slim

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

# The embedding model is downloaded now, into a folder the app user owns, so serving never
# waits for a download and still works where outbound access is restricted. The same name is
# passed to the app as EMBEDDING_MODEL, so the image cannot serve a model it did not download.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
# HF_HOME: the downloader keeps its own cache and needs a writable folder, and the app user
# has no home directory.
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    EMBEDDING_CACHE_DIR=/srv/models \
    HF_HOME=/srv/models/hf
RUN mkdir /srv/models && chown appuser /srv/models
USER appuser
RUN python -c "import os; from fastembed import TextEmbedding; TextEmbedding(os.environ['EMBEDDING_MODEL'], cache_dir=os.environ['EMBEDDING_CACHE_DIR'])"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

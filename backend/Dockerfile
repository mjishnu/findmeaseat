FROM python:3.14-slim

WORKDIR /app

# Install deps first so the layer caches across code changes.
COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY app ./app

EXPOSE 8000

# fastapi[standard] ships the `fastapi` CLI (uvicorn under the hood).
# `run` is the production server; binds 0.0.0.0:8000 by default.
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]

# Analytiq app image — same image for cloud (SaaS) and on-prem.
FROM python:3.12-slim

# system deps: build tools for some wheels; libgomp for duckdb/torch
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install python deps first (layer cache)
COPY requirements.txt .
# core deps always; sentence-transformers is heavy — installed only if ONPREM build arg set
ARG INSTALL_LOCAL_EMBEDDINGS=0
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_LOCAL_EMBEDDINGS" = "1" ]; then \
        pip install --no-cache-dir sentence-transformers; \
    fi

# app code
COPY . .

# data/uploads/docs are mounted as volumes at runtime
ENV UPLOAD_DIR=/data/uploads DOCS_DIR=/data/documents DATA_DIR=/data/files
RUN mkdir -p /data/uploads /data/documents /data/files

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fs http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]

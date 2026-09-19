FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system modelforge \
    && adduser --system --ingroup modelforge --home /home/modelforge modelforge

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY scripts ./scripts

ARG MODELFORGE_EXTRAS=""
RUN python -m pip install --no-cache-dir --upgrade pip \
    && if [ -n "$MODELFORGE_EXTRAS" ]; then \
         python -m pip install --no-cache-dir ".[$MODELFORGE_EXTRAS]"; \
       else \
         python -m pip install --no-cache-dir .; \
       fi

RUN mkdir -p /var/lib/modelforge/artifacts \
    && chown -R modelforge:modelforge /var/lib/modelforge \
    && chmod +x /app/scripts/start-api.sh

USER modelforge

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c 'import os, urllib.request; port=os.getenv("PORT","8000"); urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2).read()'

CMD ["/app/scripts/start-api.sh"]

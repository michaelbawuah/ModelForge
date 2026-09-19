FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system modelforge \
    && adduser --system --ingroup modelforge --home /home/modelforge modelforge

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY src ./src

ARG MODELFORGE_EXTRAS=""
RUN python -m pip install --no-cache-dir --upgrade pip \
    && if [ -n "$MODELFORGE_EXTRAS" ]; then \
         python -m pip install --no-cache-dir ".[$MODELFORGE_EXTRAS]"; \
       else \
         python -m pip install --no-cache-dir .; \
       fi

RUN mkdir -p /var/lib/modelforge/artifacts \
    && chown -R modelforge:modelforge /var/lib/modelforge

USER modelforge

EXPOSE 8000

CMD ["uvicorn", "modelforge.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

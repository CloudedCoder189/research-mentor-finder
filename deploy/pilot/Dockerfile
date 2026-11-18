FROM node:24-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_PUBLIC_API_BASE_URL="" NEXT_TELEMETRY_DISABLED=1
RUN npm run build && npm prune --omit=dev

FROM caddy:2 AS proxy
FROM python:3.12-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.1 \
    && python -m pip install --no-cache-dir -r requirements.txt
RUN python -m pip check && python -c "import importlib.metadata as m,json; print('RMF_RUNTIME_PACKAGES:' + json.dumps({d.metadata['Name']: d.version for d in m.distributions()}))"
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=proxy /usr/bin/caddy /usr/local/bin/caddy
COPY --from=frontend /app/frontend /app/frontend
COPY api/ ./api/
COPY services/ ./services/
COPY scrapers/ ./scrapers/
COPY database.py runtime_config.py ./
RUN python -m api.resume_smoke
COPY scripts/run_managed_api.py scripts/managed_retention.py scripts/restore_private_backup.py scripts/plan_professor_expansion.py scripts/import_reviewed_professors.py ./scripts/
COPY deploy/pilot/ ./deploy/pilot/
ENV PYTHONUNBUFFERED=1 NEXT_TELEMETRY_DISABLED=1
EXPOSE 8080
CMD ["python", "deploy/pilot/start.py"]

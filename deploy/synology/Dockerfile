FROM node:22-bookworm-slim AS qmd-runtime

# The Watcher uses QMD's BM25 path only. Avoid downloading the optional
# llama.cpp GPU runtimes (hundreds of MB) while keeping the Linux sqlite-vec
# package that QMD imports during status and search commands.
ENV NODE_LLAMA_CPP_SKIP_DOWNLOAD=true
WORKDIR /opt/qmd

RUN npm install --omit=dev --omit=optional \
        @tobilu/qmd@2.8.3 \
        sqlite-vec-linux-x64@0.1.9 \
    && /opt/qmd/node_modules/.bin/qmd --version

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=qmd-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=qmd-runtime /opt/qmd /opt/qmd

COPY deploy/synology/requirements-lock.txt /app/requirements-lock.txt
RUN python -m pip install --no-cache-dir --requirement /app/requirements-lock.txt

COPY dashboard /app/dashboard
COPY deploy/synology/entrypoint.sh /usr/local/bin/secbrain-entrypoint

RUN chmod 0555 /usr/local/bin/secbrain-entrypoint \
    && ln -s /opt/qmd/node_modules/@tobilu/qmd/bin/qmd /usr/local/bin/qmd

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; r=urlopen('http://127.0.0.1:8080/api/status', timeout=3); raise SystemExit(0 if r.status == 200 else 1)"]

ENTRYPOINT ["/usr/local/bin/secbrain-entrypoint"]
CMD ["python", "-m", "uvicorn", "dashboard_api:app", "--app-dir", "/app/dashboard/backend", "--host", "0.0.0.0", "--port", "8080"]

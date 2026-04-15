# AgentShrink — Production Dockerfile
# Deploys backend (dashboard API) + gateway as a single container
# 
# Build:  docker build -t agentshrink .
# Run:    docker run -p 8000:8000 -p 8100:8100 -v agentshrink-data:/data agentshrink
#
# Environment variables:
#   AGENTSHRINK_DB_PATH        — SQLite path (default: /data/logs.db)
#   AGENTSHRINK_OUTPUT_DIR     — Analysis output (default: /data/output)
#   AGENTSHRINK_DEPLOYMENT_MODE — "hosted" enables real auth (default: local-hosted)
#   NVIDIA_API_KEY             — For NVIDIA upstream provider
#   HF_TOKEN                   — For HuggingFace gated models
#   OPENAI_API_KEY             — For OpenAI judge model

FROM python:3.12-slim AS base

WORKDIR /app

# System deps for hdbscan/umap native builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python package
COPY pyproject.toml setup.py README.md ./
COPY agentshrink/ agentshrink/
COPY dashboard/backend/ dashboard/backend/
RUN pip install --no-cache-dir -e .

# Build frontend (if node available, otherwise skip)
FROM node:20-slim AS frontend-builder
WORKDIR /app/dashboard/frontend
COPY dashboard/frontend/package.json dashboard/frontend/package-lock.json* ./
RUN npm ci --production=false 2>/dev/null || npm install
COPY dashboard/frontend/ .
RUN npm run build

# Final image
FROM base AS production

# Copy frontend build
COPY --from=frontend-builder /app/dashboard/frontend/.next dashboard/frontend/.next
COPY --from=frontend-builder /app/dashboard/frontend/public dashboard/frontend/public
COPY --from=frontend-builder /app/dashboard/frontend/node_modules dashboard/frontend/node_modules
COPY --from=frontend-builder /app/dashboard/frontend/package.json dashboard/frontend/package.json
COPY dashboard/frontend/next.config.* dashboard/frontend/

# Copy remaining project files
COPY data/ data/
COPY .env.example .env.example

# Data directory
RUN mkdir -p /data/output
ENV AGENTSHRINK_DB_PATH=/data/logs.db
ENV AGENTSHRINK_OUTPUT_DIR=/data/output

# Expose ports
EXPOSE 8000 8100 3000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/status')" || exit 1

# Startup script
COPY <<'EOF' /app/start.sh
#!/bin/bash
set -e

echo "Starting AgentShrink stack..."

# Initialize project if not already done
if [ ! -f .agentshrink/project.json ]; then
    python -m agentshrink init \
        --project-name "${AGENTSHRINK_PROJECT_NAME:-AgentShrink Hosted}" \
        --db "${AGENTSHRINK_DB_PATH:-/data/logs.db}" \
        --output-dir "${AGENTSHRINK_OUTPUT_DIR:-/data/output}" \
        --upstream-provider "${TARGET_AGENT_PROVIDER:-mock}"
fi

# Start gateway in background
python -m agentshrink gateway \
    --host 0.0.0.0 --port 8100 \
    --db "${AGENTSHRINK_DB_PATH:-/data/logs.db}" \
    --output-dir "${AGENTSHRINK_OUTPUT_DIR:-/data/output}" &

# Start backend in background
cd /app/dashboard/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 &

# Start frontend
cd /app/dashboard/frontend
npx next start --hostname 0.0.0.0 --port 3000
EOF

RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]

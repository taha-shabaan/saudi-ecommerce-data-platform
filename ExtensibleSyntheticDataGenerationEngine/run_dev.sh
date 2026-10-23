#!/usr/bin/env bash
set -e

echo "=========================================================="
echo " Starting Extensible Synthetic Data Generation Engine"
echo "=========================================================="

# Pre-flight check: release ports if held by stale docker containers
if command -v docker >/dev/null 2>&1; then
    if [ "$(docker ps -q -f name=synthetic-engine-web)" ]; then
        echo "Stopping background Docker container 'synthetic-engine-web' on port 3000..."
        docker stop synthetic-engine-web >/dev/null 2>&1 || true
    fi
    if [ "$(docker ps -q -f name=synthetic-engine-api)" ]; then
        echo "Stopping background Docker container 'synthetic-engine-api' on port 8000..."
        docker stop synthetic-engine-api >/dev/null 2>&1 || true
    fi
fi

# Check Python environment
if [ ! -d "apps/api/.venv" ]; then
    echo "Setting up Python virtual environment..."
    python3 -m venv apps/api/.venv
    ./apps/api/.venv/bin/pip install --upgrade pip
    ./apps/api/.venv/bin/pip install -r apps/api/requirements.txt
fi

# Check Node environment
if [ ! -d "apps/web/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd apps/web && npm install && cd ../..
fi

if curl -s http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    echo "FastAPI backend is already active on http://localhost:8000."
    API_PID=""
else
    echo "Starting FastAPI backend on http://localhost:8000..."
    ./apps/api/.venv/bin/uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port 8000 --reload &
    API_PID=$!
fi

echo "Starting Next.js frontend on http://localhost:3000..."
cd apps/web && npm run dev &
WEB_PID=$!

cleanup() {
    echo "Shutting down services..."
    kill $API_PID 2>/dev/null || true
    kill $WEB_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

wait


#!/usr/bin/env bash
# Launch the NoLoop Python backend on the same port the frontends expect (4000).
set -e
cd "$(dirname "$0")"
exec uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-4000}"

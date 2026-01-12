#!/bin/bash
# Run the Xyn worker process
# This can run in the same container or separately

set -e

cd "$(dirname "$0")/.."

echo "Starting Xyn Worker..."
echo "Worker ID: ${WORKER_ID:-worker-$$}"
echo "Database: ${DATABASE_URL:-from env}"
echo

python -m core.worker

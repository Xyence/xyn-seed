#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_DIR="${ROOT_DIR%/xyn}/xyn-platform/apps/xyn-ui"
CONTAINER_NAME="${XYN_DEMO_REHEARSAL_CONTAINER:-xyn-playwright-demo}"
BASE_URL="${XYN_UI_BASE_URL:-http://localhost}"
OUT_ROOT="${XYN_DEMO_REHEARSAL_OUT:-${ROOT_DIR}/.xyn/demo-rehearsal}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="${OUT_ROOT}/${RUN_ID}"
LOG_PATH="${RUN_DIR}/rehearsal.log"

mkdir -p "${RUN_DIR}"

if [[ ! -d "${UI_DIR}" ]]; then
  echo "xyn-ui directory not found at ${UI_DIR}" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

ui_ready() {
  curl -fsS --retry 5 --retry-delay 2 --retry-connrefused "${BASE_URL}" >/dev/null 2>&1
}

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Demo rehearsal output: ${RUN_DIR}" | tee "${LOG_PATH}"

if ! ui_ready; then
  echo "==> Xyn UI not responding at ${BASE_URL}; starting local stack" | tee -a "${LOG_PATH}"
  (
    cd "${ROOT_DIR}"
    ./xynctl quickstart --force
  ) | tee -a "${LOG_PATH}"
fi

echo "==> Starting Playwright runner container" | tee -a "${LOG_PATH}"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
docker run -d --name "${CONTAINER_NAME}" --network host mcr.microsoft.com/playwright:v1.58.2-jammy sleep infinity >/dev/null
docker exec "${CONTAINER_NAME}" mkdir -p /work >/dev/null
docker cp "${UI_DIR}/." "${CONTAINER_NAME}:/work"

echo "==> Installing test dependencies" | tee -a "${LOG_PATH}"
docker exec "${CONTAINER_NAME}" bash -lc "cd /work && npm install --no-fund --no-audit" | tee -a "${LOG_PATH}"

echo "==> Running browser rehearsal" | tee -a "${LOG_PATH}"
set +e
docker exec \
  -e XYN_UI_BASE_URL="${BASE_URL}" \
  -e PLAYWRIGHT_OUTPUT_DIR="/work/test-results" \
  -e PLAYWRIGHT_REPORT_DIR="/work/playwright-report" \
  "${CONTAINER_NAME}" \
  bash -lc "cd /work && npx playwright test e2e/demo-golden-path.spec.ts" | tee -a "${LOG_PATH}"
PLAYWRIGHT_EXIT="${PIPESTATUS[0]}"
set -e

echo "==> Copying evidence" | tee -a "${LOG_PATH}"
docker cp "${CONTAINER_NAME}:/work/test-results" "${RUN_DIR}/test-results" >/dev/null 2>&1 || true
docker cp "${CONTAINER_NAME}:/work/playwright-report" "${RUN_DIR}/playwright-report" >/dev/null 2>&1 || true

echo "==> Rehearsal complete" | tee -a "${LOG_PATH}"
echo "Evidence directory: ${RUN_DIR}" | tee -a "${LOG_PATH}"
exit "${PLAYWRIGHT_EXIT}"

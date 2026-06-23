#!/bin/sh
set -e

: "${PORT:=10000}"
: "${RASA_INTERNAL_PORT:=5005}"
: "${RASA_CORS_ORIGINS:=*}"
: "${ACTION_ENDPOINT_URL:=http://localhost:5055/webhook}"

cat > endpoints.production.yml <<EOT
action_endpoint:
  url: "${ACTION_ENDPOINT_URL}"

tracker_store:
  type: SQL
  dialect: "sqlite"
  db: "rasa_tracker.db"
EOT

echo "Starting Render proxy on 0.0.0.0:${PORT}"
echo "Starting Rasa internally on 127.0.0.1:${RASA_INTERNAL_PORT}"
echo "Action endpoint: ${ACTION_ENDPOINT_URL}"

rasa run \
  --enable-api \
  --cors "${RASA_CORS_ORIGINS}" \
  --credentials credentials.yml \
  --endpoints endpoints.production.yml \
  --interface 127.0.0.1 \
  --port "${RASA_INTERNAL_PORT}" &
RASA_PID=$!

python /app/render_proxy.py --listen-port "${PORT}" --target-port "${RASA_INTERNAL_PORT}" &
PROXY_PID=$!

trap 'kill "$RASA_PID" "$PROXY_PID" 2>/dev/null || true' INT TERM

wait "$RASA_PID"
STATUS=$?
kill "$PROXY_PID" 2>/dev/null || true
exit "$STATUS"

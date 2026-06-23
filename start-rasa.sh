#!/bin/sh
set -e

: "${PORT:=5005}"
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

echo "Starting Rasa on 0.0.0.0:${PORT}"
echo "Action endpoint: ${ACTION_ENDPOINT_URL}"

rasa run \
  --enable-api \
  --cors "${RASA_CORS_ORIGINS}" \
  --credentials credentials.yml \
  --endpoints endpoints.production.yml \
  --interface 0.0.0.0 \
  --port "${PORT}"

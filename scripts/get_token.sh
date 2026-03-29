#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Fetch a Keycloak access token for local development/testing.
#
# Usage:
#   ./scripts/get_token.sh [username] [password]
#
# Defaults: alice / alice123  (pre-seeded in realm-export.json)
# ---------------------------------------------------------------------------
set -euo pipefail

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
REALM="${KEYCLOAK_REALM:-openeo}"
CLIENT_ID="${KEYCLOAK_CLIENT_ID:-workspace-service-public}"
USERNAME="${1:-alice}"
PASSWORD="${2:-alice123}"

TOKEN_URL="${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token"

echo "Fetching token from: ${TOKEN_URL}" >&2
echo "  Username: ${USERNAME}" >&2

RESPONSE=$(curl -sf -X POST "${TOKEN_URL}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=${CLIENT_ID}" \
  -d "username=${USERNAME}" \
  -d "password=${PASSWORD}")

ACCESS_TOKEN=$(echo "${RESPONSE}" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

echo ""
echo "Access token:"
echo "${ACCESS_TOKEN}"
echo ""
echo "To use with curl:"
echo "  curl -H 'Authorization: Bearer ${ACCESS_TOKEN}' http://localhost:8000/workspaces"

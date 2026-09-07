#!/bin/bash
# Start, stop, or check the local SearXNG container.
# Usage: scripts/searxng.sh up|down|restart|status|logs

set -eu

# Docker Desktop does not always link its CLI into /usr/local/bin; fall back to the app bundle.
export PATH="${PATH}:/Applications/Docker.app/Contents/Resources/bin"

COMPOSE_DIR="$(cd "$(dirname "$0")/../docker/searxng" && pwd)"
ENV_FILE="${COMPOSE_DIR}/.env"

ensure_secret() {
    if [ ! -f "${ENV_FILE}" ] || ! grep -q '^SEARXNG_SECRET=.\+' "${ENV_FILE}"; then
        printf 'SEARXNG_SECRET=%s\n' "$(openssl rand -hex 32)" >"${ENV_FILE}"
        echo "Generated ${ENV_FILE}"
    fi
}

case "${1:-status}" in
up)
    ensure_secret
    docker compose --project-directory "${COMPOSE_DIR}" up -d
    ;;
down)
    docker compose --project-directory "${COMPOSE_DIR}" down
    ;;
restart)
    ensure_secret
    docker compose --project-directory "${COMPOSE_DIR}" down
    docker compose --project-directory "${COMPOSE_DIR}" up -d
    ;;
status)
    docker compose --project-directory "${COMPOSE_DIR}" ps
    curl -fsS 'http://127.0.0.1:8080/search?q=test&format=json' >/dev/null && echo "SearXNG JSON API: ok" || echo "SearXNG JSON API: not responding"
    ;;
logs)
    docker compose --project-directory "${COMPOSE_DIR}" logs -f
    ;;
*)
    printf 'Usage: %s up|down|restart|status|logs\n' "$(basename "$0")" >&2
    exit 1
    ;;
esac

#!/bin/bash
# Start, stop, or check the local SearXNG container.
# Usage: scripts/searxng.sh up|down|off|restart|status|logs
#
# SearXNG runs only while Brave may not answer (ops/searxng_demand.py): the health check runs `up`, which starts Docker Desktop first when it is not
# running, and `off`, which also quits Docker Desktop to give back its memory (about 1.5 GB on the Studio).

set -eu

# Docker Desktop does not always link its CLI into /usr/local/bin; fall back to the app bundle.
export PATH="${PATH}:/Applications/Docker.app/Contents/Resources/bin"

COMPOSE_DIR="$(cd "$(dirname "$0")/../docker/searxng" && pwd)"
ENV_FILE="${COMPOSE_DIR}/.env"
DOCKER_START_TIMEOUT_SECONDS=180
DOCKER_STOP_TIMEOUT_SECONDS=120

ensure_secret() {
    if [ ! -f "${ENV_FILE}" ] || ! grep -q '^SEARXNG_SECRET=.\+' "${ENV_FILE}"; then
        printf 'SEARXNG_SECRET=%s\n' "$(openssl rand -hex 32)" >"${ENV_FILE}"
        echo "Generated ${ENV_FILE}"
    fi
}

docker_running() {
    docker info >/dev/null 2>&1
}

ensure_docker() {
    if ! docker_running; then
        echo "Starting Docker Desktop"
        docker desktop start --timeout "${DOCKER_START_TIMEOUT_SECONDS}"
    fi
}

case "${1:-status}" in
up)
    ensure_docker
    ensure_secret
    docker compose --project-directory "${COMPOSE_DIR}" up -d
    ;;
down)
    docker compose --project-directory "${COMPOSE_DIR}" down
    ;;
off)
    if docker_running; then
        docker compose --project-directory "${COMPOSE_DIR}" down
        docker desktop stop --timeout "${DOCKER_STOP_TIMEOUT_SECONDS}"
    fi
    echo "SearXNG and Docker Desktop are off"
    ;;
restart)
    # A deploy that changes SearXNG's settings restarts it; while it is off on purpose, it reads them when it next starts.
    if ! docker_running; then
        echo "Docker Desktop is not running, so SearXNG is off on purpose; it reads the new settings when it next starts"
        exit 0
    fi
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
    printf 'Usage: %s up|down|off|restart|status|logs\n' "$(basename "$0")" >&2
    exit 1
    ;;
esac

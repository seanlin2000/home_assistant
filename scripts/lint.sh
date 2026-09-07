#!/bin/bash

set -eu

CHECK=false
while getopts ':c' opt; do
    case "$opt" in
    c)
        CHECK=true
        ;;
    ?)
        printf 'Invalid command option.\nUsage: %s [-c]\n' "$(basename "$0")" >&2
        exit 1
        ;;
    esac
done
shift "$((OPTIND - 1))"

BLACK_OPTS=(-v --line-length 200)
ISORT_OPTS=(--profile black)

SHFMT_OPTS=(-w)
if $CHECK; then
    BLACK_OPTS+=(--check)
    ISORT_OPTS+=(--check)
    SHFMT_OPTS+=(-d)
fi

# Python: always through the project's virtual environment, never the machine's interpreter
uv run black "${BLACK_OPTS[@]}" .
uv run isort "${ISORT_OPTS[@]}" .

# Shell: every .sh file plus the git hooks, which have no extension (skip the virtual environment, which ships its own .sh files)
shell_files() {
    find . -path ./.venv -prune -o \( -name "*.sh" -o -path "./.githooks/*" \) -type f -print0
}
shell_files | xargs -0 shfmt -i 4 "${SHFMT_OPTS[@]}"
shell_files | xargs -0 shellcheck

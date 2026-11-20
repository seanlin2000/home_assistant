#!/usr/bin/env bash
# Print the prefix of the CI cache key for .cache/manual_diagrams. A cached SVG's own name covers only its source and part of the drawing code,
# so this prefix hashes everything else that shapes a rendered diagram, and CI restores only diagrams drawn by the same code and renderer:
#   - the drawing code: the diagrams package, and the cache and build hook that call it (not diagrams/sketches, the ASCII layouts figures are drawn from, which no build reads)
#   - the exact npm packages mermaid-cli resolved to (mermaid, its ELK layout and puppeteer float within mermaid-cli's version ranges)
#   - the GitHub runner image, which supplies the Chrome that draws and the fonts it measures text with
# Run it from the repository root after mermaid-cli is installed with npm.
set -euo pipefail

DRAWING_CODE=(diagrams manual_checks/diagram_cache.py manual_checks/mkdocs_hook.py ':(exclude)diagrams/sketches')

drawing_code_hashes() {
    git ls-files -z --cached --others --exclude-standard "${DRAWING_CODE[@]}" | xargs -0 shasum -a 256
}

mermaid_cli_tree() {
    local installed_tree
    installed_tree="$(npm ls --global --all --json || true)"
    # npm ls also exits non-zero over unrelated problems elsewhere in the global tree; jq -e fails only when mermaid-cli itself is missing
    jq -ce '.dependencies["@mermaid-js/mermaid-cli"]' <<<"$installed_tree"
}

code_hashes="$(drawing_code_hashes)"
installed_mermaid_cli="$(mermaid_cli_tree)"
runner_image="${ImageOS:-local}-${ImageVersion:-local}"
renderer_fingerprint="$(printf '%s\n' "$code_hashes" "$installed_mermaid_cli" "$runner_image" | shasum -a 256 | cut -c1-16)"
echo "manual-diagrams-$renderer_fingerprint-"

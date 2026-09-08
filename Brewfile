# Everything the assistant's Mac needs from Homebrew (design doc 10 §3.2). Installed by scripts/bootstrap_mac.sh with `brew bundle`.
# Versions are whatever Homebrew serves on the day; docs/VERSIONS.md records what was actually installed.

brew "git"
brew "uv"          # manages the project's Python and virtual environment (.venv), pinned by uv.lock
brew "ollama"      # runs the language model; scripts/services.sh installs our own launchd agent for it (LAN binding)
brew "espeak-ng"   # phonemizer Kokoro's text-to-speech needs
brew "rsync"       # real rsync 3.x; macOS ships openrsync, which lacks --info=progress2 and other flags
brew "shellcheck"  # scripts/lint.sh
brew "shfmt"       # scripts/lint.sh
brew "mermaid-cli" # renders the operator manual's diagrams for `uv run manual-check`; brings its own node

cask "docker-desktop"  # SearXNG container (docker/searxng)
cask "utm"             # Home Assistant OS virtual machine (scripts/haos_vm.sh)

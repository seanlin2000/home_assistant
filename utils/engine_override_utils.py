"""Per-Mac engine overrides: a file in Application Support naming the engine one Mac runs instead of the one its config names, so a rollback
needs no commit. scripts/services.sh writes and removes them; deploys never touch them."""

from pathlib import Path

from pydantic import BaseModel

OVERRIDES_DIR = Path("~/Library/Application Support/studio-assistant").expanduser()


class EngineOverride(BaseModel):
    path: Path
    engines: tuple[str, ...]
    reset_command: str  # how a person removes the file, named in the error a bad file raises

    def engine_or(self, configured: str) -> str:
        """The engine the file names, else the configured one."""
        if not self.path.is_file():
            return configured
        named = self.path.read_text().strip()
        if named not in self.engines:
            raise ValueError(f"{self.path} names {named!r}; expected one of {', '.join(self.engines)} ({self.reset_command} removes it)")
        return named

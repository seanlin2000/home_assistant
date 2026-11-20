"""What the harness keeps per conversation, in a small SQLite file so a restart loses nothing (design doc v2/04 section 3.5).

Home Assistant's chat log stays the record of what was said. The harness keeps only what Home Assistant cannot hold for it: when the conversation
was last used, and, from M3, whether it read text written by strangers. The compaction summary joins them when compaction is built.
"""

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    last_exchange_at REAL NOT NULL,
    untrusted INTEGER NOT NULL DEFAULT 0
)
"""


class ConversationState:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.execute(SCHEMA)
        self._connection.commit()

    def record_exchange(self, conversation_id: str, at: float | None = None) -> None:
        self._connection.execute(
            "INSERT INTO conversations (conversation_id, last_exchange_at) VALUES (?, ?) ON CONFLICT(conversation_id) DO UPDATE SET last_exchange_at = excluded.last_exchange_at",
            (conversation_id, time.time() if at is None else at),
        )
        self._connection.commit()

    def mark_untrusted(self, conversation_id: str) -> None:
        self._connection.execute("UPDATE conversations SET untrusted = 1 WHERE conversation_id = ?", (conversation_id,))
        self._connection.commit()

    def is_untrusted(self, conversation_id: str) -> bool:
        row = self._connection.execute("SELECT untrusted FROM conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
        return bool(row and row[0])

    def quiet_since(self, cutoff: float) -> list[str]:
        """Conversations whose last exchange came before `cutoff`: Home Assistant has forgotten them, so they have ended."""
        return [row[0] for row in self._connection.execute("SELECT conversation_id FROM conversations WHERE last_exchange_at < ?", (cutoff,))]

    def forget(self, conversation_id: str) -> None:
        self._connection.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

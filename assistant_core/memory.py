"""Seam for persistent memory. Version 1 remembers nothing between conversations; only this module changes when that decision is revisited."""

from typing import Protocol

from assistant_core.models import Message


class ConversationMemory(Protocol):
    def get_context(self, conversation: list[Message]) -> str: ...

    def remember(self, conversation: list[Message]) -> None: ...


class NoMemory:
    def get_context(self, conversation: list[Message]) -> str:
        return ""

    def remember(self, conversation: list[Message]) -> None:
        return None

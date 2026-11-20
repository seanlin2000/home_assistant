"""What each llama-server slot holds now, for the prompt cache tab (design doc v2/13 section 3.10). The slots share one pool of KV cache; the harness
budgets slot 0 for the conversation and leaves the rest of the pool to slot 1, for the router and the other quiet requests (design doc v2/02 section 3.4).
"""

from typing import Any

from pydantic import BaseModel

from assistant_core.llama_server_client import CONVERSATION_SLOT, QUIET_SLOT

SLOT_ROLES = {CONVERSATION_SLOT: "conversation", QUIET_SLOT: "router and quiet requests"}


class SlotView(BaseModel):
    slot: int
    role: str
    processing: bool
    share_tokens: int  # the part of the pool the harness budgets for this slot
    last_prompt_tokens: int | None = None  # None until the slot has served a request since the server started
    last_cached_tokens: int | None = None
    last_written_tokens: int | None = None
    holds_tokens: int | None = None  # about what the slot keeps cached: its last prompt and what was written after it


class SlotsView(BaseModel):
    pool_tokens: int
    slots: list[SlotView]


def slots_view(reported: list[dict[str, Any]], pool_tokens: int, conversation_tokens: int) -> SlotsView:
    shares = {CONVERSATION_SLOT: conversation_tokens, QUIET_SLOT: pool_tokens - conversation_tokens}
    return SlotsView(pool_tokens=pool_tokens, slots=[slot_view(slot, shares.get(slot["id"], pool_tokens)) for slot in reported])


def slot_view(reported: dict[str, Any], share_tokens: int) -> SlotView:
    """llama-server reports a slot's last request only once it has served one."""
    prompt_tokens = reported.get("n_prompt_tokens")
    written = sum(progress.get("n_decoded", 0) for progress in reported.get("next_token", [])) if prompt_tokens is not None else None
    return SlotView(
        slot=reported["id"],
        role=SLOT_ROLES.get(reported["id"], "unused"),
        processing=reported.get("is_processing", False),
        share_tokens=share_tokens,
        last_prompt_tokens=prompt_tokens,
        last_cached_tokens=reported.get("n_prompt_tokens_cache"),
        last_written_tokens=written,
        holds_tokens=prompt_tokens + written if prompt_tokens is not None else None,
    )

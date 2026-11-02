"""How long each response spent reading its prompt (prefill) and writing its answer (decode), and the average over today on this Mac's clock
(design doc v2/13 section 3.9). A response's figures add up all of its model calls, since every tool round reads and writes again."""

from datetime import datetime

from pydantic import BaseModel

from assistant_core.exchange_record import ExchangeRecord
from assistant_core.models import GenerationStats


class ResponseSpeed(BaseModel):
    prefill_seconds: float
    prefill_tokens: int  # read fresh; the cached tokens cost almost nothing, so they are left out of the speed
    cached_tokens: int
    decode_seconds: float
    decode_tokens: int


class TodaySpeed(BaseModel):
    since: str  # midnight on this Mac's clock, ISO 8601 with its offset
    responses: int
    prefill_seconds: float | None = None  # the average per response
    decode_seconds: float | None = None
    prefill_tokens_per_second: float | None = None  # all of today's tokens over all of today's seconds, so long prompts weigh more
    decode_tokens_per_second: float | None = None


def local_now() -> datetime:
    return datetime.now().astimezone()


def local_midnight(now: datetime) -> datetime:
    """Midnight of the same day, in the same offset as the time given."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def response_speed(record: ExchangeRecord) -> ResponseSpeed | None:
    """None when no model call of the exchange reported its timings."""
    timed = [stats for stats in record.model_calls if stats.prompt_eval_seconds is not None and stats.generation_seconds is not None]
    if not timed:
        return None
    return ResponseSpeed(
        prefill_seconds=sum(stats.prompt_eval_seconds for stats in timed),
        prefill_tokens=sum(fresh_tokens(stats) for stats in timed),
        cached_tokens=sum(stats.cached_prompt_tokens or 0 for stats in timed),
        decode_seconds=sum(stats.generation_seconds for stats in timed),
        decode_tokens=sum(stats.output_tokens or 0 for stats in timed),
    )


def fresh_tokens(stats: GenerationStats) -> int:
    """llama-server reports the fresh count itself; Ollama's prompt count is already only what it read."""
    if stats.fresh_prompt_tokens is not None:
        return stats.fresh_prompt_tokens
    return (stats.prompt_tokens or 0) - (stats.cached_prompt_tokens or 0)


def today_speed(records: list[ExchangeRecord], since: datetime) -> TodaySpeed:
    speeds = [speed for speed in map(response_speed, records) if speed is not None]
    if not speeds:
        return TodaySpeed(since=since.isoformat(), responses=0)
    prefill_seconds = sum(speed.prefill_seconds for speed in speeds)
    decode_seconds = sum(speed.decode_seconds for speed in speeds)
    return TodaySpeed(
        since=since.isoformat(),
        responses=len(speeds),
        prefill_seconds=prefill_seconds / len(speeds),
        decode_seconds=decode_seconds / len(speeds),
        prefill_tokens_per_second=rate(sum(speed.prefill_tokens for speed in speeds), prefill_seconds),
        decode_tokens_per_second=rate(sum(speed.decode_tokens for speed in speeds), decode_seconds),
    )


def rate(tokens: int, seconds: float) -> float | None:
    return tokens / seconds if seconds > 0 else None

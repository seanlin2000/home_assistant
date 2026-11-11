"""How long model calls spent reading their prompt (prefill) and writing (decode), shared by the exchange dashboard and the benchmark report."""

from pydantic import BaseModel

from assistant_core.models import GenerationStats


class GenerationSpeed(BaseModel):
    prefill_seconds: float
    prefill_tokens: int  # read fresh; the cached tokens cost almost nothing, so they are left out of the speed
    cached_tokens: int
    decode_seconds: float
    decode_tokens: int  # thinking included, since the model writes it at the same speed

    @property
    def prefill_tokens_per_second(self) -> float | None:
        return rate(self.prefill_tokens, self.prefill_seconds)

    @property
    def decode_tokens_per_second(self) -> float | None:
        return rate(self.decode_tokens, self.decode_seconds)


def generation_speed(model_calls: list[GenerationStats]) -> GenerationSpeed | None:
    """The calls' figures added up, or None when none of them reported its timings."""
    timed = [stats for stats in model_calls if stats.prompt_eval_seconds is not None and stats.generation_seconds is not None]
    if not timed:
        return None
    return GenerationSpeed(
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


def rate(tokens: int, seconds: float) -> float | None:
    return tokens / seconds if seconds > 0 else None

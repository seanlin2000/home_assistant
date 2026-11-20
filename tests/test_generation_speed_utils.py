from assistant_core.models import GenerationStats
from utils.generation_speed_utils import generation_speed


def timed_call(fresh_tokens: int, prefill_seconds: float, written_tokens: int, decode_seconds: float) -> GenerationStats:
    return GenerationStats(
        model="m",
        total_seconds=1.0,
        fresh_prompt_tokens=fresh_tokens,
        cached_prompt_tokens=100,
        output_tokens=written_tokens,
        prompt_eval_seconds=prefill_seconds,
        generation_seconds=decode_seconds,
    )


def test_the_rates_weigh_each_call_by_its_size_not_one_vote_each() -> None:
    speed = generation_speed([timed_call(2000, 2.0, 20, 1.0), timed_call(100, 1.0, 180, 9.0)])
    assert (speed.prefill_tokens_per_second, speed.decode_tokens_per_second) == (700.0, 20.0)
    assert speed.cached_tokens == 200


def test_calls_without_timings_give_no_speed() -> None:
    assert generation_speed([GenerationStats(model="m", total_seconds=1.0)]) is None

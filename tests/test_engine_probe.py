from assistant_core.models import GenerationStats
from benchmark.engine_probe import MemorySnapshot, ProbeResult, decode_rate, prefill_rate, table_row

GIB = 1024**3
MEMORY = MemorySnapshot(server_bytes=5 * GIB, compressed_bytes=0, unused_bytes=GIB, swap_used_bytes=0)


def probe_result(cached_after_router: int) -> ProbeResult:
    return ProbeResult(
        label="strata-dflash2",
        short_prompt_tokens=6300,
        short_prefill_rates=[1200.0, 1260.0, 1300.0],
        long_prompt_tokens=12300,
        long_prefill_rates=[1100.0],
        decode_rates=[90.0, 95.5, 99.0],
        first_turn_prompt_tokens=6400,
        cached_after_router=cached_after_router,
        memory_before=MEMORY,
        memory_after=MEMORY.model_copy(update={"server_bytes": 7 * GIB}),
    )


def test_prefill_counts_only_the_tokens_read_fresh_and_decode_every_token_written() -> None:
    stats = GenerationStats(model="m", total_seconds=9, fresh_prompt_tokens=6000, cached_prompt_tokens=300, prompt_eval_seconds=5.0, output_tokens=200, generation_seconds=2.5)
    assert (prefill_rate(stats), decode_rate(stats)) == (1200.0, 80.0)
    assert prefill_rate(GenerationStats(model="m", total_seconds=1)) == 0.0


def test_a_row_shows_the_medians_and_whether_the_conversation_stayed_cached() -> None:
    row = table_row(probe_result(cached_after_router=6380))
    assert "| strata-dflash2 | 1260 (6300) | 1100 (12300) | 95.5 | 6380 of 6400, holds | 5.0 GiB → 7.0 GiB | 1.0 GiB | 0.0 GiB → 0.0 GiB |" == row
    assert "LOST" in table_row(probe_result(cached_after_router=300))

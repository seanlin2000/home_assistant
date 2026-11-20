from assistant_core.models import GenerationStats, Transcript
from benchmark.bake_off import RunFigures, first_request_fresh_tokens, fresh_criterion, score_criterion, slowest_tenth, spoken_criterion
from benchmark.records import Category


def figures(total: int, spoken: list[float], fresh: list[int]) -> RunFigures:
    return RunFigures(
        total=total,
        category_totals={category: 0 for category in Category},
        exchanges=len(spoken),
        malformed_exchanges=0,
        empty_completion_exchanges=0,
        first_spoken_seconds=spoken,
        first_request_fresh_tokens=fresh,
        decode_rates=[],
    )


def test_the_score_floor_is_the_baseline_mean_minus_its_spread() -> None:
    baseline = [figures(200, [1.0], []), figures(210, [1.0], []), figures(220, [1.0], [])]
    _, measured, met = score_criterion(baseline, [figures(191, [0.4], [])])
    assert measured == "mean 191.0 against a floor of 190.0" and met
    assert score_criterion(baseline, [figures(189, [0.4], [])])[2] is False


def test_the_first_spoken_word_must_come_in_half_the_time() -> None:
    assert spoken_criterion([figures(0, [8.0, 10.0, 12.0], [])], [figures(0, [4.0, 5.0, 6.0], [])])[2]
    assert not spoken_criterion([figures(0, [8.0, 10.0, 12.0], [])], [figures(0, [5.0, 5.1, 6.0], [])])[2]


def test_nine_first_requests_in_ten_must_read_at_most_600_tokens_fresh() -> None:
    assert fresh_criterion([figures(0, [], [200] * 9 + [2400])])[2]
    assert not fresh_criterion([figures(0, [], [200] * 8 + [2400, 2400])])[2]


def test_the_first_request_is_the_first_response_request_of_the_exchange() -> None:
    calls = [GenerationStats(model="m", total_seconds=1, fresh_prompt_tokens=180), GenerationStats(model="m", total_seconds=1, fresh_prompt_tokens=700)]
    assert first_request_fresh_tokens(Transcript(model="m", system_prompt="", conversation=[], model_calls=calls)) == 180
    assert slowest_tenth([float(value) for value in range(1, 11)]) == 10.0

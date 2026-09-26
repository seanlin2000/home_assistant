"""Dollar estimates for the frontier baseline's paid API calls. Prices are Claude Opus 5 list prices per million tokens; update if the baseline model changes."""

INPUT_USD_PER_MILLION = 5.0
OUTPUT_USD_PER_MILLION = 25.0


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return input_tokens / 1_000_000 * INPUT_USD_PER_MILLION + output_tokens / 1_000_000 * OUTPUT_USD_PER_MILLION

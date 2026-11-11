from benchmark.records import load_config
from benchmark.run import CONFIG_PATH, candidate_policy


def test_a_llama_server_candidate_takes_its_models_sampling_for_its_thinking() -> None:
    config = load_config(CONFIG_PATH)
    policy = candidate_policy(config.candidate("qwen3.8-27b-medium"), config)
    assert (policy.think, policy.temperature, policy.top_k, policy.max_output_tokens) == ("medium", 1.0, 20, 2048)
    assert policy.route_questions is False and policy.history_exchanges == 6


def test_an_ollama_candidate_keeps_the_shared_temperature_and_ollamas_defaults() -> None:
    config = load_config(CONFIG_PATH)
    policy = candidate_policy(config.candidate("gemma4-e4b"), config)
    assert (policy.temperature, policy.top_k) == (config.policy.temperature, None)

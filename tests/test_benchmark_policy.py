from benchmark.records import load_config
from benchmark.run import CONFIG_PATH, candidate_policy, candidate_sampling
from serving.settings import load_serving_config


def test_a_llama_server_candidate_takes_its_models_sampling_for_its_thinking() -> None:
    config = load_config(CONFIG_PATH)
    policy = candidate_policy(config.candidate("qwen3.8-27b-medium"), config)
    assert (policy.think, policy.temperature, policy.top_k, policy.max_output_tokens) == ("medium", 1.0, 20, 4096)
    assert policy.route_questions is False and policy.history_exchanges == 6


def test_a_llama_server_candidate_budgets_against_its_models_conversation_slot_as_the_harness_does() -> None:
    config = load_config(CONFIG_PATH)
    policy = candidate_policy(config.candidate("qwen3.8-flash-next-low"), config)
    assert policy.context_tokens == load_serving_config().models["qwen3.8-flash-next"].conversation_tokens
    assert candidate_policy(config.candidate("gemma4-e4b"), config).context_tokens == config.policy.context_tokens


def test_an_ollama_candidate_keeps_the_shared_temperature_and_ollamas_defaults() -> None:
    config = load_config(CONFIG_PATH)
    policy = candidate_policy(config.candidate("gemma4-e4b"), config)
    assert (policy.temperature, policy.top_k) == (config.policy.temperature, None)


def test_run_metadata_records_the_sampling_a_candidate_ran_with() -> None:
    config = load_config(CONFIG_PATH)
    sampling = candidate_sampling(config.candidate("qwen3.8-27b-medium"), config)
    assert sampling == {"think": "medium", "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0, "repeat_penalty": 1.0, "max_output_tokens": 4096}

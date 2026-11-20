"""Raw speed per candidate: prompt processing and generation rates at a short and a long prompt. Hardware projection, not quality."""

import argparse
import asyncio
from pathlib import Path

import ollama
from rich.console import Console
from rich.table import Table

from benchmark.ollama_utils import ensure_model_present, unload, warm_up
from benchmark.records import load_config

CONFIG_PATH = Path("benchmark/config.yaml")
FILLER_SENTENCE = "The quick brown fox jumps over the lazy dog while the committee reviews quarterly figures and debates the merits of unified memory. "
PROMPT_WORD_TARGETS = {"short": 400, "long": 3000}
GENERATION_TOKENS = 128
console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure tokens per second and time to first token per candidate.")
    parser.add_argument("--candidate", action="append", help="candidate key; repeatable; default all Ollama candidates")
    parser.add_argument("--run", required=True, help="results folder name (version_1, version_2, ...)")
    return parser.parse_args()


def main() -> None:
    asyncio.run(main_async(parse_args()))


async def main_async(args: argparse.Namespace) -> None:
    config = load_config(CONFIG_PATH)
    candidates = [candidate for candidate in config.candidates if candidate.provider == "ollama" and (not args.candidate or candidate.key in args.candidate)]
    client = ollama.AsyncClient(host=config.services.ollama_host)
    rows = []
    for candidate in candidates:
        await ensure_model_present(client, candidate.model)
        fit = await warm_up(client, candidate.model, config.policy.context_tokens)
        for prompt_name, word_target in PROMPT_WORD_TARGETS.items():
            rows.append((candidate.key, prompt_name, fit.fully_on_gpu, await measure(client, candidate.model, word_target, config.policy.context_tokens)))
        await unload(client, candidate.model)
    table = render_table(rows)
    console.print(table)
    write_markdown(Path(config.services.results_dir) / args.run / "speed.md", rows)


async def measure(client: ollama.AsyncClient, model: str, word_target: int, context_tokens: int) -> ollama.GenerateResponse:
    prompt = (FILLER_SENTENCE * (word_target // len(FILLER_SENTENCE.split()) + 1)) + "\n\nSummarize the text above in one sentence."
    return await client.generate(model=model, prompt=prompt, options={"num_predict": GENERATION_TOKENS, "num_ctx": context_tokens, "temperature": 0}, keep_alive="10m")


def rate(count: int | None, duration_ns: int | None) -> float:
    return count / (duration_ns / 1e9) if count and duration_ns else 0.0


def render_table(rows: list) -> Table:
    table = Table(title="Raw speed on this machine")
    for column in ("Candidate", "Prompt", "Prompt tokens", "Prompt tok/s", "Time to first token", "Gen tok/s", "Fully on GPU"):
        table.add_column(column)
    for key, prompt_name, on_gpu, response in rows:
        table.add_row(
            key,
            prompt_name,
            str(response.prompt_eval_count),
            f"{rate(response.prompt_eval_count, response.prompt_eval_duration):.0f}",
            f"{(response.prompt_eval_duration or 0) / 1e9:.2f} s",
            f"{rate(response.eval_count, response.eval_duration):.1f}",
            str(on_gpu),
        )
    return table


def write_markdown(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Raw speed", "", "| Candidate | Prompt | Prompt tokens | Prompt tok/s | Time to first token | Gen tok/s | Fully on GPU |", "|---|---|---|---|---|---|---|"]
    for key, prompt_name, on_gpu, response in rows:
        lines.append(
            f"| {key} | {prompt_name} | {response.prompt_eval_count} | {rate(response.prompt_eval_count, response.prompt_eval_duration):.0f} | {(response.prompt_eval_duration or 0) / 1e9:.2f} s | {rate(response.eval_count, response.eval_duration):.1f} | {on_gpu} |"
        )
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

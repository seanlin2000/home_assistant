"""Sketch: Benchmarking, the benchmark end to end as one line. The five steps run top to bottom in a single column, and each file one step writes for the next is the label on the arrow between them. The two files the run starts from sit above it; the files a person edits for later steps sit in the right column beside the step that reads them."""

from canvas import Canvas

CONTENT_WIDTH = 20
BOX_WIDTH = CONTENT_WIDTH + 4
MAIN = 28
SIDE = MAIN + BOX_WIDTH + 22
PITCH = 7
canvas = Canvas(SIDE + BOX_WIDTH // 2 + 2, 8 * PITCH)


def place(y: int, center: int, lines: list[str], stored: bool = False) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines], stored=stored)


def down(upper: tuple[int, int, int], label: str = "") -> None:
    canvas.vline(MAIN, upper[2] + 1, upper[2] + PITCH - 4)
    if label:
        canvas.put(upper[2] + 2, MAIN + 2, label)


config = place(0, MAIN - 14, ["config.yaml", "the candidates"], stored=True)
questions = place(0, MAIN + 14, ["questions.yaml", "28 questions"], stored=True)
run = place(PITCH, MAIN, ["benchmark-run", "asks each question"])
export = place(2 * PITCH, MAIN, ["judge --export", "harness gates"])
subagent = place(3 * PITCH, MAIN, ["judge subagent", "in Claude Code"])
verify = place(4 * PITCH, MAIN, ["judge --import", "checks each verdict"])
report = place(5 * PITCH, MAIN, ["benchmark-report", "scores candidates"])
standings = place(6 * PITCH, MAIN, ["report.md", "the standings"], stored=True)
rubric = place(3 * PITCH, SIDE, ["rubric.md", "5 gates, 3 scores"], stored=True)
sheet = place(5 * PITCH, SIDE, ["review_sheet.yaml", "20% to check by hand"], stored=True)

canvas.vline(MAIN - 8, config[2] + 1, PITCH - 1)
canvas.vline(MAIN + 8, questions[2] + 1, PITCH - 1)
down(run, "key.jsonl: a transcript per question")
down(export, "judge_cases/key/: a case per question")
down(subagent, "qid.verdict.json: a verdict per case")
down(verify, "key.scores.jsonl: gates and scores")
down(report)

canvas.hline(3 * PITCH + 2, subagent[1] + 1, rubric[0] - 1, head="◀")
canvas.hline(5 * PITCH + 1, report[1] + 1, sheet[0] - 1, head="▶")
canvas.put(5 * PITCH, report[1] + 3, "writes a sample")
canvas.hline(5 * PITCH + 2, report[1] + 1, sheet[0] - 1, head="◀")
canvas.put(5 * PITCH + 3, report[1] + 3, "your checks")

canvas.grid = canvas.grid[: standings[2] + 1]
print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))

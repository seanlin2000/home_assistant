import numpy

from benchmark.voice_latency import VoiceAnswer, median_of, rate_of, sample_averages, shorten_pauses, spoken_answer

PAGES_PER_MB = 64  # 16 KiB pages


def sample(epoch: float, label: str = "llama-1", swapins: int = 0, wired_pages: int = 65536) -> dict[str, str]:
    row = {"epoch": str(epoch), "label": label, "phase": "burst", "swap_used_mb": "2048", "swapins": str(swapins), "swapouts": "0", "pageins": "0"}
    row |= {"wired_pages": str(wired_pages), "compressor_pages": "0", "pressure_free_percent": "12"}
    return row | {f"{name}{suffix}": "1024" for name in ("engine", "speech", "kokoro", "vm") for suffix in ("_mb", "_cmprs_mb")}


def test_a_counter_becomes_mb_per_minute_over_consecutive_samples_only() -> None:
    rows = [sample(0, swapins=0), sample(30, swapins=PAGES_PER_MB * 10), sample(600, swapins=PAGES_PER_MB * 1000)]
    assert rate_of(rows, "swapins") == 20.0  # 10 MB in 30 s; the 570 s gap is another stretch of the setup's samples, not a rate


def test_each_setup_gets_its_own_averages_in_the_order_it_ran() -> None:
    table = sample_averages([sample(0, "strata-1", wired_pages=0), sample(5, "llama-1"), sample(10, "llama-1")])
    rows = table.splitlines()[2:]
    assert [row.split(" | ")[0] for row in rows] == ["| strata-1", "| llama-1"]
    assert " 1.0 " in rows[1]  # 65,536 wired pages of 16 KiB are 1 GB


def test_a_stage_that_never_happened_is_left_out_of_the_median() -> None:
    answers = [VoiceAnswer(label="x", question_id="A11", first_audio_seconds=2.0), VoiceAnswer(label="x", question_id="A77", first_audio_seconds=4.0), VoiceAnswer(label="x", question_id="B90")]
    assert median_of(answers, "first_audio_seconds") == "3.00"
    assert median_of(answers, "stt_seconds") == "–"


def test_the_spoken_answer_is_read_from_the_intent_output() -> None:
    assert spoken_answer({"intent_output": {"response": {"speech": {"plain": {"speech": "It fell in 1989."}}}}}) == "It fell in 1989."
    assert spoken_answer({}) == ""


def test_a_long_pause_between_sentences_is_cut_to_a_quarter_second() -> None:
    tone = (numpy.sin(numpy.arange(16000) / 5) * 10000).astype(numpy.int16)  # one second of speech-loud sound
    pause = numpy.zeros(16000, dtype=numpy.int16)  # one second of silence
    shortened = shorten_pauses(numpy.concatenate([tone, pause, tone]))
    kept_pause_seconds = (len(shortened) - 2 * 16000) / 16000
    assert 0.2 <= kept_pause_seconds <= 0.25  # whole 20 ms frames, so just under a quarter second

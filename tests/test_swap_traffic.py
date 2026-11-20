"""The swap traffic of the last minute, from readings of vm_stat's counters since boot (design doc v2/13 section 3.11)."""

from dashboard.swap_traffic import SwapCounters, SwapReading, SwapTraffic, SwapWindow

MIB = 1024**2


def reading(taken_at: float, read_back_mib: int, written_out_mib: int) -> SwapReading:
    return SwapReading(taken_at=taken_at, counters=SwapCounters(read_back_bytes=read_back_mib * MIB, written_out_bytes=written_out_mib * MIB))


def window_of(*readings: SwapReading) -> SwapWindow:
    window = SwapWindow()
    for each in readings:
        window.record(each)
    return window


def test_no_readings_yet_report_nothing_over_no_time() -> None:
    assert SwapWindow().traffic() == SwapTraffic(read_back_bytes=0, written_out_bytes=0, window_seconds=0.0)


def test_one_reading_reports_nothing_over_no_time() -> None:
    assert window_of(reading(10.0, 500, 900)).traffic() == SwapTraffic(window_seconds=0.0)


def test_readings_under_a_minute_apart_report_the_change_over_the_time_they_span() -> None:
    traffic = window_of(reading(10.0, 500, 900), reading(14.0, 502, 900), reading(18.0, 503, 910)).traffic()
    assert traffic == SwapTraffic(read_back_bytes=3 * MIB, written_out_bytes=10 * MIB, window_seconds=8.0)


def test_a_full_minute_counts_from_the_reading_a_minute_back() -> None:
    traffic = window_of(reading(0.0, 500, 900), reading(30.0, 510, 900), reading(60.0, 520, 905)).traffic()
    assert traffic == SwapTraffic(read_back_bytes=20 * MIB, written_out_bytes=5 * MIB, window_seconds=60.0)


def test_readings_older_than_a_minute_are_dropped() -> None:
    traffic = window_of(reading(0.0, 100, 100), reading(40.0, 500, 900), reading(70.0, 520, 905), reading(100.0, 530, 905)).traffic()
    assert traffic == SwapTraffic(read_back_bytes=30 * MIB, written_out_bytes=5 * MIB, window_seconds=60.0)


def test_a_gap_longer_than_a_minute_starts_the_window_again() -> None:
    traffic = window_of(reading(0.0, 100, 100), reading(4.0, 110, 100), reading(500.0, 900, 900)).traffic()
    assert traffic == SwapTraffic(window_seconds=0.0)

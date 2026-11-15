"""Whether the model's wired memory will stay wired. macOS 26 and later unwire GPU memory about 2 s after a process's last GPU work, and MLX
renews it only when RESIDENCY_REFRESH_VARIABLE is in the environment at startup (scripts/services.sh sets it for the speech agent). MLX reads it
once, before the first GPU allocation, so setting it from Python after import has no effect."""

RESIDENCY_REFRESH_VARIABLE = "MLX_METAL_RESIDENCY_REFRESH_INTERVAL_MS"


def wiring_summary(wired_limit_mib: int, refresh_interval_ms: str | None) -> str:
    if refresh_interval_ms and refresh_interval_ms.isdigit() and int(refresh_interval_ms) > 0:
        return f"wired limit {wired_limit_mib} MiB, residency renewed every {refresh_interval_ms} ms"
    return f"wired limit {wired_limit_mib} MiB, but {RESIDENCY_REFRESH_VARIABLE} is not set: on macOS 26 and later the model is unwired about 2 s after each call"

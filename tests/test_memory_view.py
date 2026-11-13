"""The memory tab: this Mac's RAM split into pieces that add up to it, each app counting only what it holds in RAM, the Home Assistant setup found and
given the part of its model files in RAM, everything else grouped by app, and one reading shared by every page that asks (design
doc v2/13 section 3.11)."""

from pathlib import Path

import httpx

from assistant_service.exchange_log import ExchangeLog, TraceLog
from dashboard.app import build_app
from dashboard.exchange_views import ExchangeStore
from dashboard.memory_reader import MemoryReader
from dashboard.memory_views import MemoryOutputs, memory_view, size_in_bytes
from dashboard.model_memory import ModelFileMemory, ModelMemory
from ops.pipeline_runs import PipelineRunLog

GIB = 1024**3
MODEL_WEIGHTS_BYTES = 5 * GIB
TOP = """Processes: 6 total, 1 running, 5 sleeping, 400 threads
PhysMem: 15G used (8083M wired, 4602M compressor), 94M unused.

PID    MEM    CMPRS
101    512M+  128M
102    4096M  3840M
103    3G     1G
104    100M-  60M
105    1024M  0B
106    2M     0B
107    96M    32M
"""
EXECUTABLES = """  101 /opt/homebrew/bin/llama-server
  102 /Applications/UTM.app/Contents/XPCServices/QEMUHelper.xpc/Contents/MacOS/QEMULauncher.app/Contents/MacOS/QEMULauncher
  103 /Applications/Firefox.app/Contents/MacOS/firefox
  104 /Users/me/home_assistant/.venv/bin/python
  105 /Applications/Firefox.app/Contents/MacOS/plugin-container.app/Contents/MacOS/plugin-container
  106 /bin/zsh
  107 /Users/me/home_assistant/.venv/bin/python
"""
COMMAND_LINES = """  101 /opt/homebrew/bin/llama-server --port 8090 -m /models/gemma.gguf
  102 /Applications/UTM.app/Contents/XPCServices/QEMUHelper.xpc/Contents/MacOS/QEMULauncher.app/Contents/MacOS/QEMULauncher
  103 /Applications/Firefox.app/Contents/MacOS/firefox
  104 /Users/me/home_assistant/.venv/bin/python /Users/me/home_assistant/.venv/bin/assistant-service
  105 /Applications/Firefox.app/Contents/MacOS/plugin-container.app/Contents/MacOS/plugin-container -childID 3
  106 /bin/zsh -c cd /Users/me/home_assistant && .venv/bin/exchange-dashboard
  107 /Users/me/home_assistant/.venv/bin/python /Users/me/home_assistant/.venv/bin/exchange-dashboard
"""
VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                4624.
Pages wired down:                        131072.
Pages purgeable:                          16384.
"Translation faults":               22081456363.
File-backed pages:                        65536.
Anonymous pages:                         262144.
Pages occupied by compressor:             65536.
"""
SYSCTL = """17179869184
total = 2048.00M  used = 1024.50M  free = 1023.50M  (encrypted)
Apple M1 Pro
"""


def served(resident_bytes: int) -> ModelMemory:
    return ModelMemory(
        files=[ModelFileMemory(name="model.gguf", resident_bytes=resident_bytes, size_bytes=resident_bytes)],
        kv_cache_bytes=GIB,
        context_tokens=32768,
        slots=2,
        prompt_cache_limit_bytes=GIB,
    )


class ServedModel:
    """The served model as the memory reader measures it, which changes when another model is served."""

    def __init__(self, resident_bytes: int) -> None:
        self.resident_bytes = resident_bytes
        self.readable = True

    async def current(self) -> ModelMemory:
        if not self.readable:
            raise FileNotFoundError("model.gguf")
        return served(self.resident_bytes)


def outputs() -> MemoryOutputs:
    return MemoryOutputs(top=TOP, executables=EXECUTABLES, command_lines=COMMAND_LINES, vm_stat=VM_STAT, sysctl=SYSCTL, computer_name="Studio\n")


def test_sizes_read_with_their_units_and_growth_marks() -> None:
    assert [size_in_bytes(text) for text in ["512M+", "3G", "100M-", "12K", "0B", "N/A"]] == [512 * 1024**2, 3 * GIB, 100 * 1024**2, 12 * 1024, 0, None]


def test_the_pieces_add_up_to_the_macs_ram() -> None:
    view = memory_view(outputs(), served(MODEL_WEIGHTS_BYTES))
    machine = view.machine
    page = 16384
    assert (machine.name, machine.chip, machine.total_bytes) == ("Studio", "Apple M1 Pro", 16 * GIB)
    assert (machine.compressed_bytes, machine.file_cache_bytes, machine.unused_bytes) == (65536 * page, (65536 + 16384) * page, 4624 * page)
    pieces = [view.setup_ram_bytes, view.others_ram_bytes, machine.compressed_bytes, machine.macos_bytes, machine.file_cache_bytes, machine.unused_bytes]
    assert machine.macos_bytes > 0 and sum(pieces) == machine.total_bytes
    assert (machine.swap_used_bytes, machine.swap_total_bytes) == (round(1024.5 * 1024**2), 2048 * 1024**2)


def test_an_app_counts_only_what_it_holds_in_ram_and_the_rest_as_compressed_or_on_disk() -> None:
    view = memory_view(outputs(), served(MODEL_WEIGHTS_BYTES))
    home_assistant = next(group for group in view.setup if group.name == "Home Assistant VM (UTM)")
    assert (home_assistant.ram_bytes, home_assistant.compressed_bytes) == (256 * 1024**2, 3840 * 1024**2)
    assert [(group.name, group.processes, group.ram_bytes, group.compressed_bytes) for group in view.others] == [("Firefox", 2, 3 * GIB, GIB), ("zsh", 1, 2 * 1024**2, 0)]


def test_the_setup_adds_llama_servers_model_weights_and_lists_components_not_running() -> None:
    view = memory_view(outputs(), served(MODEL_WEIGHTS_BYTES))
    by_name = {group.name: group for group in view.setup}
    llama = by_name["llama-server"]
    assert (llama.ram_bytes, llama.model_weights_bytes, llama.compressed_bytes) == (384 * 1024**2 + MODEL_WEIGHTS_BYTES, MODEL_WEIGHTS_BYTES, 128 * 1024**2)
    assert llama.model_memory == served(MODEL_WEIGHTS_BYTES)
    assert (by_name["harness"].processes, by_name["Kokoro, text to speech"].processes) == (1, 0)
    assert view.setup[0].name == "llama-server"
    assert view.setup_ram_bytes == sum(group.ram_bytes for group in view.setup)


def test_a_shell_that_started_a_service_is_not_counted_as_the_service() -> None:
    by_name = {group.name: group for group in memory_view(outputs(), served(MODEL_WEIGHTS_BYTES)).setup}
    assert (by_name["exchange dashboard"].processes, by_name["exchange dashboard"].ram_bytes) == (1, 64 * 1024**2)


def test_macos_share_is_never_negative_when_the_apps_claim_more_than_is_left() -> None:
    assert memory_view(outputs(), served(20 * GIB)).machine.macos_bytes == 0


async def test_one_reading_serves_every_page_for_a_few_seconds() -> None:
    reads = []
    now = [100.0]

    async def read_outputs() -> MemoryOutputs:
        reads.append(now[0])
        return outputs()

    reader = MemoryReader(read_outputs, ServedModel(MODEL_WEIGHTS_BYTES), clock=lambda: now[0])
    await reader.current()
    now[0] += 2
    await reader.current()
    now[0] += 3
    await reader.current()
    assert reads == [100.0, 105.0]


async def test_the_served_model_is_measured_at_every_reading_so_a_model_switch_shows_at_the_next() -> None:
    now = [100.0]
    loaded = ServedModel(MODEL_WEIGHTS_BYTES)

    async def read_outputs() -> MemoryOutputs:
        return outputs()

    reader = MemoryReader(read_outputs, loaded, clock=lambda: now[0])
    before = await reader.current()
    loaded.resident_bytes = 15 * GIB
    now[0] += 5
    after = await reader.current()
    assert [view.setup[0].model_weights_bytes for view in (before, after)] == [MODEL_WEIGHTS_BYTES, 15 * GIB]


async def test_a_served_model_whose_files_cannot_be_read_shows_llama_server_without_its_weights_and_says_so() -> None:
    loaded = ServedModel(MODEL_WEIGHTS_BYTES)
    loaded.readable = False

    async def read_outputs() -> MemoryOutputs:
        return outputs()

    llama = next(group for group in (await MemoryReader(read_outputs, loaded).current()).setup if group.name == "llama-server")
    assert (llama.model_weights_bytes, llama.ram_bytes) == (0, 384 * 1024**2)
    assert llama.note == "model weights not counted: the served model's files, named in config/serving.toml, could not be read"


async def test_the_api_serves_the_memory_view_or_says_why_it_cannot(tmp_path: Path) -> None:
    store = ExchangeStore(ExchangeLog(tmp_path / "exchanges"), TraceLog(tmp_path / "traces"), PipelineRunLog(tmp_path / "pipeline_runs"))

    async def read_outputs() -> MemoryOutputs:
        return outputs()

    async def unreadable() -> MemoryOutputs:
        raise OSError("top: not found")

    def client_with(reader: MemoryReader | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app(store, ["mac.lan:8775"], memory=reader)), base_url="http://mac.lan:8775")

    async with client_with(MemoryReader(read_outputs, ServedModel(MODEL_WEIGHTS_BYTES))) as client:
        view = (await client.get("/api/memory")).json()
    async with client_with(MemoryReader(unreadable, ServedModel(MODEL_WEIGHTS_BYTES))) as client:
        failed = await client.get("/api/memory")
    async with client_with(None) as client:
        off = await client.get("/api/memory")
    assert view["machine"]["name"] == "Studio" and view["setup"][0]["name"] == "llama-server"
    assert (failed.status_code, failed.json()["error"]) == (503, "this Mac's memory could not be read: OSError: top: not found")
    assert off.status_code == 503

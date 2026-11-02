"""The memory tab: this Mac's memory split as Activity Monitor splits it, the Home Assistant setup's processes found and added up with llama-server's
model weights, everything else grouped by app, and one reading shared by every page that asks (design doc v2/13 section 3.11)."""

from pathlib import Path

import httpx

from assistant_service.exchange_log import ExchangeLog, TraceLog
from dashboard.app import build_app
from dashboard.exchange_views import ExchangeStore
from dashboard.memory_reader import MemoryReader
from dashboard.memory_views import MemoryOutputs, memory_view, size_in_bytes
from ops.pipeline_runs import PipelineRunLog

GIB = 1024**3
MODEL_FILE_BYTES = 5 * GIB
TOP = """Processes: 6 total, 1 running, 5 sleeping, 400 threads
PhysMem: 15G used (8083M wired, 4602M compressor), 94M unused.

PID    MEM
101    512M+
102    4096M
103    3G
104    100M-
105    1024M
106    2M
107    96M
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
IOREG = """+-o AGXAcceleratorG13X  <class AGXAcceleratorG13X>
    {
      "PerformanceStatistics" = {"In use system memory"=6164348928,"Alloc system memory"=7000000000}
    }
"""


def outputs() -> MemoryOutputs:
    return MemoryOutputs(top=TOP, executables=EXECUTABLES, command_lines=COMMAND_LINES, vm_stat=VM_STAT, sysctl=SYSCTL, ioreg=IOREG, computer_name="Studio\n")


def test_sizes_read_with_their_units_and_growth_marks() -> None:
    assert [size_in_bytes(text) for text in ["512M+", "3G", "100M-", "12K", "0B", "N/A"]] == [512 * 1024**2, 3 * GIB, 100 * 1024**2, 12 * 1024, 0, None]


def test_the_mac_is_split_the_way_activity_monitor_splits_it() -> None:
    machine = memory_view(outputs(), MODEL_FILE_BYTES).machine
    page = 16384
    assert (machine.name, machine.chip, machine.total_bytes) == ("Studio", "Apple M1 Pro", 16 * GIB)
    assert machine.app_bytes == (262144 - 16384) * page
    assert machine.wired_bytes == 131072 * page
    assert machine.compressed_bytes == 65536 * page
    assert machine.cached_files_bytes == (65536 + 16384) * page
    assert machine.free_bytes == 16 * GIB - (245760 + 131072 + 65536 + 81920) * page
    assert (machine.swap_used_bytes, machine.swap_total_bytes) == (round(1024.5 * 1024**2), 2048 * 1024**2)
    assert machine.gpu_in_use_bytes == 6164348928


def test_the_setup_adds_llama_servers_model_weights_and_lists_components_not_running() -> None:
    view = memory_view(outputs(), MODEL_FILE_BYTES)
    by_name = {group.name: group for group in view.setup}
    llama = by_name["llama-server"]
    assert (llama.footprint_bytes, llama.model_weights_bytes, llama.total_bytes) == (512 * 1024**2, MODEL_FILE_BYTES, 512 * 1024**2 + MODEL_FILE_BYTES)
    assert by_name["Home Assistant VM (UTM)"].total_bytes == 4 * GIB
    assert by_name["harness"].processes == 1
    assert by_name["Kokoro, text to speech"].processes == 0
    assert view.setup[0].name == "llama-server"
    assert view.setup_bytes == sum(group.total_bytes for group in view.setup)


def test_a_shell_that_started_a_service_is_not_counted_as_the_service() -> None:
    by_name = {group.name: group for group in memory_view(outputs(), MODEL_FILE_BYTES).setup}
    assert (by_name["exchange dashboard"].processes, by_name["exchange dashboard"].footprint_bytes) == (1, 96 * 1024**2)


def test_everything_else_is_grouped_by_app() -> None:
    others = memory_view(outputs(), MODEL_FILE_BYTES).others
    assert [(group.name, group.processes, group.total_bytes) for group in others] == [("Firefox", 2, 4 * GIB), ("zsh", 1, 2 * 1024**2)]


async def test_one_reading_serves_every_page_for_a_few_seconds() -> None:
    reads = []
    now = [100.0]

    async def read_outputs() -> MemoryOutputs:
        reads.append(now[0])
        return outputs()

    reader = MemoryReader(read_outputs, MODEL_FILE_BYTES, clock=lambda: now[0])
    await reader.current()
    now[0] += 2
    await reader.current()
    now[0] += 3
    await reader.current()
    assert reads == [100.0, 105.0]


async def test_the_api_serves_the_memory_view_or_says_why_it_cannot(tmp_path: Path) -> None:
    store = ExchangeStore(ExchangeLog(tmp_path / "exchanges"), TraceLog(tmp_path / "traces"), PipelineRunLog(tmp_path / "pipeline_runs"))

    async def read_outputs() -> MemoryOutputs:
        return outputs()

    async def unreadable() -> MemoryOutputs:
        raise OSError("top: not found")

    def client_with(reader: MemoryReader | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app(store, ["mac.lan:8775"], memory=reader)), base_url="http://mac.lan:8775")

    async with client_with(MemoryReader(read_outputs, MODEL_FILE_BYTES)) as client:
        view = (await client.get("/api/memory")).json()
    async with client_with(MemoryReader(unreadable, MODEL_FILE_BYTES)) as client:
        failed = await client.get("/api/memory")
    async with client_with(None) as client:
        off = await client.get("/api/memory")
    assert view["machine"]["name"] == "Studio" and view["setup"][0]["name"] == "llama-server"
    assert (failed.status_code, failed.json()["error"]) == (503, "this Mac's memory could not be read: OSError: top: not found")
    assert off.status_code == 503

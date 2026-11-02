"""This Mac's memory, and how much of it the Home Assistant setup takes, for the memory tab (design doc v2/13 section 3.11).

Each process's size is its physical footprint, the figure Activity Monitor shows: what the process allocated itself, compressed and swapped-out
memory included, so on a Mac under pressure the footprints add up to more than its RAM. llama-server's model weights are the exception: they are
mapped from the model file and held by the GPU, outside the footprint, so the model file's size is added to llama-server's.
"""

import re
from collections import defaultdict
from pathlib import PurePosixPath

from pydantic import BaseModel

OTHER_GROUPS_SHOWN = 7
UNIT_BYTES = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
SIZE = re.compile(r"^(\d+(?:\.\d+)?)([BKMGT])[+-]?$")
SWAP_FIELD = re.compile(r"(total|used) = (\d+(?:\.\d+)?)([KMGT])")
GPU_IN_USE = re.compile(r'"In use system memory"=(\d+)')
VM_STAT_LINE = re.compile(r'^"?([^":]+)"?:\s+(\d+)\.?$')
PAGE_SIZE = re.compile(r"page size of (\d+) bytes")
APP_BUNDLE = re.compile(r"/([^/]+)\.app/")
LLAMA_SERVER = "llama-server"


class SetupComponent(BaseModel):
    name: str
    pattern: str  # searched in the program a process runs (see program_text)


SETUP_COMPONENTS = [
    SetupComponent(name=LLAMA_SERVER, pattern=r"/llama-server\b"),
    SetupComponent(name="Home Assistant VM (UTM)", pattern=r"/QEMULauncher\b"),
    SetupComponent(name="Whisper, speech to text", pattern=r"wyoming-mlx-whisper"),
    SetupComponent(name="Kokoro, text to speech", pattern=r"kokoro-server"),
    SetupComponent(name="harness", pattern=r"assistant-service"),
    SetupComponent(name="tool server", pattern=r"assistant-mcp"),
    SetupComponent(name="exchange dashboard", pattern=r"exchange-dashboard"),
    SetupComponent(name="Docker Desktop, which runs SearXNG", pattern=r"/Docker\.app/|com\.apple\.Virtualization\.VirtualMachine"),
]


class MemoryOutputs(BaseModel):
    """What macOS's own tools print, none of which needs root."""

    top: str  # top -l 1 -stats pid,mem
    executables: str  # ps -axww -o pid=,comm=
    command_lines: str  # ps -axww -o pid=,args=
    vm_stat: str
    sysctl: str  # sysctl -n hw.memsize vm.swapusage machdep.cpu.brand_string
    ioreg: str  # ioreg -r -d 1 -w 0 -c IOAccelerator
    computer_name: str


class MachineMemory(BaseModel):
    """Split the way Activity Monitor splits it."""

    name: str
    chip: str
    total_bytes: int
    app_bytes: int
    wired_bytes: int
    compressed_bytes: int
    cached_files_bytes: int
    free_bytes: int
    swap_used_bytes: int
    swap_total_bytes: int
    gpu_in_use_bytes: int | None  # memory the GPU holds, part of wired; most of it is the model's weights


class ProcessGroup(BaseModel):
    name: str
    processes: int
    footprint_bytes: int
    model_weights_bytes: int = 0  # llama-server's weights, mapped from the model file and outside its footprint
    total_bytes: int


class MemoryView(BaseModel):
    machine: MachineMemory
    setup: list[ProcessGroup]  # every component, running or not, largest first
    setup_bytes: int
    others: list[ProcessGroup]  # the largest other apps, then the rest as one group
    others_bytes: int


class RunningProcess(BaseModel):
    pid: int
    executable: str
    command_line: str
    footprint_bytes: int


def memory_view(outputs: MemoryOutputs, model_file_bytes: int | None) -> MemoryView:
    processes = running_processes(outputs)
    setup_processes = {component.name: [process for process in processes if matches(component, process)] for component in SETUP_COMPONENTS}
    claimed = {process.pid for members in setup_processes.values() for process in members}
    setup = sorted((setup_group(name, members, model_file_bytes) for name, members in setup_processes.items()), key=lambda group: -group.total_bytes)
    others = other_groups([process for process in processes if process.pid not in claimed])
    return MemoryView(
        machine=machine_memory(outputs),
        setup=setup,
        setup_bytes=sum(group.total_bytes for group in setup),
        others=others,
        others_bytes=sum(group.total_bytes for group in others),
    )


def running_processes(outputs: MemoryOutputs) -> list[RunningProcess]:
    footprints = footprints_by_pid(outputs.top)
    executables = text_by_pid(outputs.executables)
    command_lines = text_by_pid(outputs.command_lines)
    return [
        RunningProcess(pid=pid, executable=executable, command_line=command_lines.get(pid, executable), footprint_bytes=footprints[pid]) for pid, executable in executables.items() if pid in footprints
    ]


def footprints_by_pid(top_output: str) -> dict[int, int]:
    """top's rows after its PID and MEM header; a size can carry a trailing + or - for growing or shrinking."""
    rows = top_output.split("\nPID", 1)[-1].splitlines()[1:]
    footprints = {}
    for row in rows:
        fields = row.split()
        if len(fields) >= 2 and fields[0].isdigit() and (size := size_in_bytes(fields[1])) is not None:
            footprints[int(fields[0])] = size
    return footprints


def size_in_bytes(text: str) -> int | None:
    match = SIZE.match(text)
    return round(float(match.group(1)) * UNIT_BYTES[match.group(2)]) if match else None


def text_by_pid(ps_output: str) -> dict[int, str]:
    rows = (line.strip().split(maxsplit=1) for line in ps_output.splitlines() if line.strip())
    return {int(fields[0]): fields[1] for fields in rows if len(fields) == 2 and fields[0].isdigit()}


def matches(component: SetupComponent, process: RunningProcess) -> bool:
    return re.search(component.pattern, program_text(process)) is not None


def program_text(process: RunningProcess) -> str:
    """The executable and the first two words of its command line: a shell that started a service names it further along, so it is not the service."""
    return f"{process.executable}\n{' '.join(process.command_line.split()[:2])}"


def setup_group(name: str, members: list[RunningProcess], model_file_bytes: int | None) -> ProcessGroup:
    footprint = sum(process.footprint_bytes for process in members)
    weights = (model_file_bytes or 0) if name == LLAMA_SERVER and members else 0
    return ProcessGroup(name=name, processes=len(members), footprint_bytes=footprint, model_weights_bytes=weights, total_bytes=footprint + weights)


def other_groups(processes: list[RunningProcess]) -> list[ProcessGroup]:
    """Grouped by app, so Chrome's twenty helpers count as Chrome; the largest few are named, and the rest are one group."""
    by_app: dict[str, list[RunningProcess]] = defaultdict(list)
    for process in processes:
        by_app[app_name(process.executable)].append(process)
    groups = sorted((plain_group(name, members) for name, members in by_app.items()), key=lambda group: -group.total_bytes)
    shown, rest = groups[:OTHER_GROUPS_SHOWN], groups[OTHER_GROUPS_SHOWN:]
    if not rest:
        return shown
    rest_processes = sum(group.processes for group in rest)
    rest_bytes = sum(group.total_bytes for group in rest)
    return [*shown, ProcessGroup(name=f"{len(rest)} smaller apps and tools", processes=rest_processes, footprint_bytes=rest_bytes, total_bytes=rest_bytes)]


def app_name(executable: str) -> str:
    """The outermost app bundle the executable lives in, or its file name."""
    bundle = APP_BUNDLE.search(executable)
    return bundle.group(1) if bundle else PurePosixPath(executable).name


def plain_group(name: str, members: list[RunningProcess]) -> ProcessGroup:
    footprint = sum(process.footprint_bytes for process in members)
    return ProcessGroup(name=name, processes=len(members), footprint_bytes=footprint, total_bytes=footprint)


def machine_memory(outputs: MemoryOutputs) -> MachineMemory:
    """App memory is anonymous memory that cannot be purged; cached files are file pages and purgeable memory, which macOS frees first."""
    page_size, pages = vm_stat_pages(outputs.vm_stat)
    total_text, swap_text, chip = (outputs.sysctl.splitlines() + ["", "", ""])[:3]
    total = int(total_text)
    app = (pages.get("Anonymous pages", 0) - pages.get("Pages purgeable", 0)) * page_size
    wired = pages.get("Pages wired down", 0) * page_size
    compressed = pages.get("Pages occupied by compressor", 0) * page_size
    cached_files = (pages.get("File-backed pages", 0) + pages.get("Pages purgeable", 0)) * page_size
    swap = swap_sizes(swap_text)
    gpu = GPU_IN_USE.search(outputs.ioreg)
    return MachineMemory(
        name=outputs.computer_name.strip(),
        chip=chip.strip(),
        total_bytes=total,
        app_bytes=app,
        wired_bytes=wired,
        compressed_bytes=compressed,
        cached_files_bytes=cached_files,
        free_bytes=max(total - app - wired - compressed - cached_files, 0),
        swap_used_bytes=swap.get("used", 0),
        swap_total_bytes=swap.get("total", 0),
        gpu_in_use_bytes=int(gpu.group(1)) if gpu else None,
    )


def vm_stat_pages(vm_stat_output: str) -> tuple[int, dict[str, int]]:
    page_size = PAGE_SIZE.search(vm_stat_output)
    rows = (VM_STAT_LINE.match(line.strip()) for line in vm_stat_output.splitlines()[1:])
    return int(page_size.group(1)) if page_size else 4096, {row.group(1): int(row.group(2)) for row in rows if row}


def swap_sizes(swap_text: str) -> dict[str, int]:
    """sysctl's "total = 15360.00M  used = 14477.31M  free = 882.69M"."""
    return {field: round(float(amount) * UNIT_BYTES[unit]) for field, amount, unit in SWAP_FIELD.findall(swap_text)}

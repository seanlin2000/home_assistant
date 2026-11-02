"""This Mac's RAM, and how much of it the Home Assistant setup holds, for the memory tab (design doc v2/13 section 3.11).

The tab splits the RAM into pieces that add up to it: what each app holds in RAM as-is, llama-server's model weights, the compressed memory of every
app packed together, macOS itself, and what is free. An app's physical footprint, the figure Activity Monitor shows, also counts what macOS has
compressed for it or moved to disk, so footprints can add up to far more than the RAM; `top` reports that part per process, and the footprint minus
it is what the app holds in RAM. llama-server's model weights are mapped from the model file and held by the GPU, outside any footprint, so the size
llama-server reports for its loaded model is added to its own.
"""

import re
from collections import defaultdict
from pathlib import PurePosixPath

from pydantic import BaseModel

OTHER_GROUPS_SHOWN = 7
UNIT_BYTES = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
SIZE = re.compile(r"^(\d+(?:\.\d+)?)([BKMGT])[+-]?$")
SWAP_FIELD = re.compile(r"(total|used) = (\d+(?:\.\d+)?)([KMGT])")
VM_STAT_LINE = re.compile(r'^"?([^":]+)"?:\s+(\d+)\.?$')
PAGE_SIZE = re.compile(r"page size of (\d+) bytes")
APP_BUNDLE = re.compile(r"/([^/]+)\.app/")
LLAMA_SERVER = "llama-server"
UNKNOWN_WEIGHTS_NOTE = "model weights not counted: llama-server did not say which model it has loaded"


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

    top: str  # top -l 1 -stats pid,mem,cmprs
    executables: str  # ps -axww -o pid=,comm=
    command_lines: str  # ps -axww -o pid=,args=
    vm_stat: str
    sysctl: str  # sysctl -n hw.memsize vm.swapusage machdep.cpu.brand_string
    computer_name: str


class MachineMemory(BaseModel):
    """The parts of the RAM no single app owns. With the apps' own RAM they add up to `total_bytes`."""

    name: str
    chip: str
    total_bytes: int
    compressed_bytes: int  # the RAM every app's compressed memory takes, packed together; macOS does not say whose is whose
    macos_bytes: int  # the remainder: the system itself, and memory no single app owns
    file_cache_bytes: int  # copies of files, which macOS drops the moment anything needs room
    unused_bytes: int
    swap_used_bytes: int
    swap_total_bytes: int


class ProcessGroup(BaseModel):
    name: str
    processes: int
    ram_bytes: int  # held in RAM as-is, llama-server's model weights included
    compressed_bytes: int  # compressed in RAM or moved to disk, which `top` does not tell apart
    model_weights_bytes: int = 0
    note: str = ""


class MemoryView(BaseModel):
    machine: MachineMemory
    setup: list[ProcessGroup]  # every component, running or not, most RAM first
    setup_ram_bytes: int
    others: list[ProcessGroup]  # the apps holding the most RAM, then the rest as one group
    others_ram_bytes: int


class ProcessMemory(BaseModel):
    ram_bytes: int
    compressed_bytes: int


class RunningProcess(BaseModel):
    pid: int
    executable: str
    command_line: str
    memory: ProcessMemory


def memory_view(outputs: MemoryOutputs, model_weights_bytes: int | None) -> MemoryView:
    processes = running_processes(outputs)
    setup_processes = {component.name: [process for process in processes if matches(component, process)] for component in SETUP_COMPONENTS}
    claimed = {process.pid for members in setup_processes.values() for process in members}
    setup_groups = (setup_group(name, members, model_weights_bytes) for name, members in setup_processes.items())
    setup = sorted(setup_groups, key=lambda group: (-group.ram_bytes, -group.compressed_bytes))
    others = other_groups([process for process in processes if process.pid not in claimed])
    setup_ram = sum(group.ram_bytes for group in setup)
    others_ram = sum(group.ram_bytes for group in others)
    return MemoryView(machine=machine_memory(outputs, setup_ram + others_ram), setup=setup, setup_ram_bytes=setup_ram, others=others, others_ram_bytes=others_ram)


def running_processes(outputs: MemoryOutputs) -> list[RunningProcess]:
    sizes = sizes_by_pid(outputs.top)
    executables = text_by_pid(outputs.executables)
    command_lines = text_by_pid(outputs.command_lines)
    return [RunningProcess(pid=pid, executable=executable, command_line=command_lines.get(pid, executable), memory=sizes[pid]) for pid, executable in executables.items() if pid in sizes]


def sizes_by_pid(top_output: str) -> dict[int, ProcessMemory]:
    """top's rows after its PID, MEM, and CMPRS header."""
    rows = (row.split() for row in top_output.split("\nPID", 1)[-1].splitlines()[1:])
    sizes = {int(fields[0]): row_memory(fields[1], fields[2]) for fields in rows if len(fields) >= 3 and fields[0].isdigit()}
    return {pid: memory for pid, memory in sizes.items() if memory is not None}


def row_memory(footprint_text: str, compressed_text: str) -> ProcessMemory | None:
    """The footprint less what is compressed or on disk is what the process holds in RAM as-is."""
    footprint, compressed = size_in_bytes(footprint_text), size_in_bytes(compressed_text)
    if footprint is None or compressed is None:
        return None
    return ProcessMemory(ram_bytes=max(footprint - compressed, 0), compressed_bytes=compressed)


def size_in_bytes(text: str) -> int | None:
    """A size as top prints it; a trailing + or - marks one growing or shrinking."""
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


def setup_group(name: str, members: list[RunningProcess], model_weights_bytes: int | None) -> ProcessGroup:
    group = plain_group(name, members)
    if name != LLAMA_SERVER or not members:
        return group
    if model_weights_bytes is None:
        return group.model_copy(update={"note": UNKNOWN_WEIGHTS_NOTE})
    return group.model_copy(update={"model_weights_bytes": model_weights_bytes, "ram_bytes": group.ram_bytes + model_weights_bytes})


def other_groups(processes: list[RunningProcess]) -> list[ProcessGroup]:
    """Grouped by app, so Chrome's twenty helpers count as Chrome; the few holding the most RAM are named, and the rest are one group."""
    by_app: dict[str, list[RunningProcess]] = defaultdict(list)
    for process in processes:
        by_app[app_name(process.executable)].append(process)
    groups = sorted((plain_group(name, members) for name, members in by_app.items()), key=lambda group: -group.ram_bytes)
    shown, rest = groups[:OTHER_GROUPS_SHOWN], groups[OTHER_GROUPS_SHOWN:]
    if not rest:
        return shown
    return [*shown, merged_group(f"{len(rest)} smaller apps and tools", rest)]


def merged_group(name: str, groups: list[ProcessGroup]) -> ProcessGroup:
    return ProcessGroup(
        name=name,
        processes=sum(group.processes for group in groups),
        ram_bytes=sum(group.ram_bytes for group in groups),
        compressed_bytes=sum(group.compressed_bytes for group in groups),
    )


def app_name(executable: str) -> str:
    """The outermost app bundle the executable lives in, or its file name."""
    bundle = APP_BUNDLE.search(executable)
    return bundle.group(1) if bundle else PurePosixPath(executable).name


def plain_group(name: str, members: list[RunningProcess]) -> ProcessGroup:
    ram = sum(process.memory.ram_bytes for process in members)
    compressed = sum(process.memory.compressed_bytes for process in members)
    return ProcessGroup(name=name, processes=len(members), ram_bytes=ram, compressed_bytes=compressed)


def machine_memory(outputs: MemoryOutputs, held_by_apps: int) -> MachineMemory:
    """macOS's share is what is left once the apps, the compressed memory, the file cache, and the unused pages are counted, so the parts add up."""
    page_size, pages = vm_stat_pages(outputs.vm_stat)
    total_text, swap_text, chip = (outputs.sysctl.splitlines() + ["", "", ""])[:3]
    total = int(total_text)
    compressed = pages.get("Pages occupied by compressor", 0) * page_size
    file_cache = (pages.get("File-backed pages", 0) + pages.get("Pages purgeable", 0)) * page_size
    unused = pages.get("Pages free", 0) * page_size
    swap = swap_sizes(swap_text)
    return MachineMemory(
        name=outputs.computer_name.strip(),
        chip=chip.strip(),
        total_bytes=total,
        compressed_bytes=compressed,
        macos_bytes=max(total - held_by_apps - compressed - file_cache - unused, 0),
        file_cache_bytes=file_cache,
        unused_bytes=unused,
        swap_used_bytes=swap.get("used", 0),
        swap_total_bytes=swap.get("total", 0),
    )


def vm_stat_pages(vm_stat_output: str) -> tuple[int, dict[str, int]]:
    page_size = PAGE_SIZE.search(vm_stat_output)
    rows = (VM_STAT_LINE.match(line.strip()) for line in vm_stat_output.splitlines()[1:])
    return int(page_size.group(1)) if page_size else 4096, {row.group(1): int(row.group(2)) for row in rows if row}


def swap_sizes(swap_text: str) -> dict[str, int]:
    """sysctl's "total = 15360.00M  used = 14477.31M  free = 882.69M"."""
    return {field: round(float(amount) * UNIT_BYTES[unit]) for field, amount, unit in SWAP_FIELD.findall(swap_text)}

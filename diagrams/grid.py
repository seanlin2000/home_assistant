"""Laying a rendered Mermaid flowchart out on the fixed grid its own source declares, for a drawing whose placement carries meaning no layout engine can be asked for.

The source names the grid in `%%` comments, which Mermaid ignores and a snippet include carries along, one line per row, the ids in column order and `.` for an empty cell:

    %% grid: puck    stt      intents  agent    tts
    %% grid: .       whisper  ma       ollama   kokoro

Columns are as wide as their widest box and rows as tall as their tallest, so a box always sits under the box it belongs to. Ids joined by `+` in one cell (`weights+kv`) are a group: they stand side by side, the group centred in the cell, and it may reach into the empty cells beside it without widening its column, so the boxes it hangs under keep their spacing. An id written in neighbouring cells of one row (`.  puck  puck  .`) spans them, centred over the stretch without widening either column; its edges land in the centre of the box at their other end, and a labelled one crosses the gutter half a row gap from it, its label right of the leg into (or out of) that box. An id written in the same column of neighbouring rows spans them, centred between them without heightening either. A box feeding boxes both above and below it in the next column fans out: one line leaves its side for a trunk just past its column, and a branch runs from the trunk into the side of each box, its label on the branch. Several boxes in one column whose unlabelled edges all reach one box in a later column, level with the topmost of them or above it, fan in: each leaves its right side for one trunk in the gap, just outside any container around their column alone and inside the machine around them, and the trunk enters the target's side, joining a straight line already entering there so the target gets one arrowhead. A box named on a `%% join:` line (`%% join: protect`) gathers the unlabelled edges from the boxes above it in its own column the same way: each leaves its right side for one trunk just past the column, inside the innermost container holding them all, and the trunk enters the joined box's right side under one arrowhead, instead of each line passing beside the boxes in between. Elbows out of one box toward one side, into different rows, each leave at a point of their own, the nearest row's closest to the targets, so the farther ones run under the nearer ones' corners, each label right of its own drop. An edge down a column with a box in between passes beside that box, out of the source's side, and lands on the top of the box below, which widens until the line lands well inside its corner. In a left-to-right figure, outside every container, an edge to a later step one row down drops and turns into its side, and one to a later column higher up runs along its row and rises into the target's bottom. A box written `<kokoro` or `piper>` hangs under the left or right half of its column, moved half its own width to that side, so two boxes under one stage, a row apart, each have a stretch of their own and the lower one's lines pass beside the upper one. A device above a machine, hanging over a box it has no edge with, sends its edges into the boxes beside that one the way a sketch draws them: down through the container tops under the device, across inside the innermost container below its title, and into the centre of the box's top, each label right of its line above the containers. A detour, a box fed from the row above that also feeds back into it, hanging under a box it has no edge with is tucked: an edge from the row above comes down that box's centre line and into the tucked box's side, and an edge to the row above leaves by its side and rises into the other box's centre, each label right of the vertical line. An empty cell may name a subgraph after its dot (`.mac`): it stays empty, but that container reaches over it, so a sketch's machine can enclose the stretch an edge runs through below its boxes. Each subgraph becomes a container wrapping the cells of everything inside it, with its title in a strip above them that no label is placed in, and top-level containers that start or end in the same row share that top or bottom edge. Every edge is redrawn as an orthogonal line through the gutters between the cells. Two neighbours that send each other something get two parallel lines, and the edge written first runs above the centre line (in a row) or left of it (in a column), so the sketch, not the direction, decides which way round the pair reads. A vertical pair's labels sit outside their lines, below the last container border the pair crosses when it passes a row on the way, and the containers around them reach far enough to keep each label clear of their border. A `%% peers:` line names boxes that are peers, such as the steps of one chain (`%% peers: results download extract sources`): each box, cylinder, or stadium takes the widest one's width and the tallest one's height about its own centre, so its text stays centred, and the gaps between them are evened to the widest. Nothing else about the drawing is touched: the boxes keep the fills, strokes, classes, and text Mermaid gave them, and only peers change size.
"""

import re
from collections import Counter
from itertools import combinations, permutations, product
from typing import NamedTuple

from diagrams.polish import CLUSTER, FRAME, NUMBER, TITLE_INSET, Box, Title, cluster_markup, title_of

GRID_ROW = re.compile(r"^\s*%%\s*grid:\s*(?P<cells>\S.*?)\s*$")
PEERS_ROW = re.compile(r"^\s*%%\s*peers:\s*(?P<names>\S.*?)\s*$")
LEFT_TO_RIGHT = re.compile(r"^\s*flowchart\s+LR\b", re.MULTILINE)
COLUMN_GAP_ROW = re.compile(r"^\s*%%\s*column-gap:\s*(?P<pixels>\d+(?:\.\d+)?)\s*$")
JOIN_ROW = re.compile(r"^\s*%%\s*join:\s*(?P<names>\S.*?)\s*$")
SUBGRAPH = re.compile(r"^\s*subgraph\s+(?P<id>\w+)")
BLOCK_END = re.compile(r"^\s*end\s*$")
NODE_LINE = re.compile(r"^\s*(?P<id>\w+)\s*[\[({]")
NODE_TRANSFORM = re.compile(r'(?P<head><g class="node[^"]*" id="[^"]*flowchart-(?P<name>\w+)-\d+"[^>]*transform="translate\()(?P<x>[\d.\-]+), *(?P<y>[\d.\-]+)(?P<tail>\))')
NODE_RECT = re.compile(r'<rect class="basic label-container"[^>]*x="(?P<x>-?[\d.]+)" y="(?P<y>-?[\d.]+)" width="(?P<width>[\d.]+)" height="(?P<height>[\d.]+)"')
SHAPE_PATH = re.compile(r'<g class="basic label-container[^"]*"><path d="(?P<d>[^"]+)"')
BARE_SHAPE_PATH = re.compile(r'<path d="(?P<d>[^"]+)"[^>]*class="basic label-container(?:[^>]*transform="translate\((?P<tx>-?[\d.]+), *(?P<ty>-?[\d.]+)\)")?')
NODE_POLYGON = re.compile(r'<polygon points="(?P<d>[^"]+)" class="label-container"(?:[^>]*transform="translate\((?P<tx>-?[\d.]+), *(?P<ty>-?[\d.]+)\)")?')
CYLINDER_TOP = re.compile(r"^M0,(?P<ry>[\d.]+) a")
STADIUM_OUTLINES = re.compile(r'(?P<head><g class="basic label-container outer-path">)(?P<outlines>(?:<path [^>]*/>)+)')
PATH_DRAWING = re.compile(r'd="[^"]*"')
PATH_SEGMENT = re.compile(r"([MmLlHhVvAaZz])([^MmLlHhVvAaZz]*)")
EDGE_PATH = re.compile(r'(?P<head><path d=")(?P<d>[^"]+)(?P<tail>" id="[^"]*-L_(?P<link>\w+)_\d+")')
EDGE_MARKER = re.compile(r'(?P<path><path d="[^"]*" id="[^"]*-L_(?P<link>\w+)_\d+"[^>]*?) marker-end="[^"]*"')
EDGE_LABEL = re.compile(
    r'(?P<head><g class="edgeLabel" transform="translate\()(?P<x>[\d.\-]+), (?P<y>[\d.\-]+)'
    r'(?P<tail>\)"><g class="label" data-id="L_(?P<link>\w+)_\d+"[^>]*><foreignObject width="(?P<width>[\d.]+)" height="(?P<height>[\d.]+)")'
)
EMPTY_CELL = "."
GROUP_JOIN = "+"
HANG_LEFT = "<"
HANG_RIGHT = ">"
GROUP_GAP = 32
COLUMN_GAP = 76
ROW_GAP = 64
CONTAINER_PAD = 18
TITLE_GAP = 12
LABEL_CLEARANCE = 14
MARGIN = 24
ARROW_GAP = 4
ATTACHMENT_FRACTION = 0.25
OPPOSING_OFFSET = 20
LANE_GAP = 20
SHARED_LINE_WEIGHT = 100
LABEL_MARGIN = 6
ENTRY_ROOM = 32
TRUNK_OFFSET = 24
BESIDE_GAP = 28
LANDING_INSET = 28
SAME_LINE_TOLERANCE = 0.5
LABEL_POSITIONS = (0.5, 0.45, 0.55, 0.4, 0.6, 0.35, 0.65, 0.3, 0.7, 0.25, 0.75, 0.2, 0.8, 0.15, 0.85, 0.1, 0.9, 0.05, 0.95)


class Cell(NamedTuple):
    row: int
    column: int


class Span(NamedTuple):
    start: float
    size: float

    @property
    def end(self) -> float:
        return self.start + self.size

    @property
    def center(self) -> float:
        return self.start + self.size / 2


class Container(NamedTuple):
    id: str
    members: frozenset[str]
    children: tuple[str, ...]


class OpenBlock(NamedTuple):
    id: str
    members: set[str]
    children: list[str]


class Edge(NamedTuple):
    link: str
    source: str
    target: str
    label: Box | None


class Lane(NamedTuple):
    departure_x: float
    arrival_x: float
    level: float


class Stub(NamedTuple):
    edge: Edge
    departs: bool


class FanIn(NamedTuple):
    target: str
    column: int
    legs: tuple[Edge, ...]
    folders: int
    host: str | None


class Trunk(NamedTuple):
    x: float
    join_y: float
    lands: bool


class Drawing(NamedTuple):
    grid: list[list[str]]
    sizes: dict[str, Box]
    containers: list[Container]
    titles: dict[str, Title]
    edges: list[Edge]
    diamonds: frozenset[str]
    peers: list[list[str]]
    column_gap: float
    lane_room: dict[int, float]
    hangs: dict[str, int]
    left_to_right: bool
    joins: frozenset[str]


class Sheet(NamedTuple):
    grid: list[list[str]]
    cells: dict[str, Cell]
    columns: list[Span]
    rows: list[Span]
    channels_x: list[float]
    channels_y: list[float]
    boxes: dict[str, Box]
    containers: dict[str, Box]
    strips: dict[str, float]
    title_widths: dict[str, float]
    anchors: dict[str, tuple[float, float]]
    diamonds: frozenset[str]
    opposed: dict[tuple[str, str], float]
    bus_legs: frozenset[tuple[str, str]]
    lanes: dict[tuple[str, str], Lane]
    spanned: dict[str, tuple[int, int]]
    tucked: frozenset[str]
    entries: dict[tuple[str, str], tuple[str, ...]]
    fans: dict[tuple[str, str], tuple[float, float]]
    passes: dict[tuple[str, str], float]
    left_to_right: bool
    trunks: dict[tuple[str, str], Trunk]
    departures: dict[tuple[str, str], float]


def grid_rows(source: str) -> list[list[str]]:
    return [match["cells"].split() for line in source.splitlines() if (match := GRID_ROW.match(line))]


def hanging_sides(grid: list[list[str]]) -> dict[str, int]:
    return {plain_token(token): hanging_side(token) for line in grid for token in line if hanging_side(token)}


def hanging_side(token: str) -> int:
    return -1 if token.startswith(HANG_LEFT) else 1 if token.endswith(HANG_RIGHT) else 0
    # `<kokoro` hangs under the left half of the box above it and `piper>` under the right half, so two boxes under one stage, a row apart, each keep a stretch of their own.


def plain_token(token: str) -> str:
    return token.strip(HANG_LEFT + HANG_RIGHT)


def plain_grid(grid: list[list[str]]) -> list[list[str]]:
    return [[plain_token(token) for token in line] for line in grid]


def peer_rows(source: str) -> list[list[str]]:
    return [match["names"].split() for line in source.splitlines() if (match := PEERS_ROW.match(line))]


def column_gap_of(source: str) -> float:
    return max([float(match["pixels"]) for line in source.splitlines() if (match := COLUMN_GAP_ROW.match(line))] + [COLUMN_GAP])
    # Two figures meant to be compared side by side declare one gap wide enough for either's widest label, so their boxes land in the same places.


def join_targets(source: str) -> frozenset[str]:
    return frozenset(name for line in source.splitlines() if (match := JOIN_ROW.match(line)) for name in match["names"].split())
    # A box named on a `%% join:` line gathers the edges from the boxes above it in its own column into one trunk beside the column, entering its side, as a sketch draws checks joining at a gate.


def lay_out_on_grid(svg: str, source: str) -> str:
    joins = join_targets(source)
    svg = with_room_to_land(with_equal_peers(svg, peer_rows(source)), grid_rows(source), joins)
    markups = node_markups(svg)
    sizes = {name: shape_size(markup) for name, markup in markups.items()}
    diamonds = frozenset(name for name, markup in markups.items() if NODE_POLYGON.search(markup))
    rows = grid_rows(source)
    drawing = Drawing(
        plain_grid(rows),
        sizes,
        containers_of(source),
        cluster_titles(svg),
        edges_of(svg, set(sizes)),
        diamonds,
        peer_rows(source),
        column_gap_of(source),
        {},
        hanging_sides(rows),
        bool(LEFT_TO_RIGHT.search(source)),
        joins,
    )
    sheet = laned_sheet(drawing)
    routes = {edge.link: route_points(sheet, edge.source, edge.target) for edge in drawing.edges}
    titles_x = title_x_positions(sheet, routes)
    labels = label_boxes(sheet, drawing.edges, routes, titles_x)
    joined = frozenset(edge.link for edge in drawing.edges if (edge.source, edge.target) in sheet.trunks and not sheet.trunks[(edge.source, edge.target)].lands)
    return reframe(draw_labels(draw_edges(draw_containers(move_nodes(svg, sheet), sheet, titles_x), routes, joined), labels), sheet, routes, labels)


def node_markups(svg: str) -> dict[str, str]:
    matches = list(NODE_TRANSFORM.finditer(svg))
    starts = [match.end() for match in matches] + [len(svg)]
    return {match["name"]: svg[starts[index] : starts[index + 1]] for index, match in enumerate(matches)}


def shape_size(markup: str) -> Box:
    rect = NODE_RECT.search(markup)
    if rect is not None:
        return Box(float(rect["x"]), float(rect["y"]), float(rect["width"]), float(rect["height"]))
    shape = SHAPE_PATH.search(markup) or NODE_POLYGON.search(markup) or BARE_SHAPE_PATH.search(markup)
    drawn = shape["d"] if shape["d"].lstrip()[0].isalpha() else "M" + shape["d"]
    box = path_bbox(drawn)
    offsets = shape.groupdict()
    return Box(box.x + float(offsets.get("tx") or 0), box.y + float(offsets.get("ty") or 0), box.width, box.height)
    # The box is the shape's node coordinates: a cylinder or diamond is drawn from a corner and centred by its own transform, which the bbox must include.


def with_equal_peers(svg: str, peers: list[list[str]]) -> str:
    for names in peers:
        svg = resized_nodes(svg, names, largest_shape(svg, names))
    return svg


def with_room_to_land(svg: str, rows: list[list[str]], joins: frozenset[str]) -> str:
    sizes = {name: shape_size(markup) for name, markup in node_markups(svg).items()}
    grid = plain_grid(rows)
    cells = first_cells(grid)
    for (source, target), _ in passes_of(grid, cells, unjoined(edges_of(svg, set(sizes)), cells, joins), set(hanging_sides(rows))).items():
        passed = [source] + passed_boxes(grid, cells, source, target)
        needed = 2 * (max(sizes[name].width for name in passed) / 2 + BESIDE_GAP + LANDING_INSET)
        if sizes[target].width < needed:
            svg = resized_nodes(svg, [target], Box(0, 0, needed, sizes[target].height))
    return svg
    # A line passing beside the boxes in its way lands on the top of a box at least as wide as them, the way a sketch draws a base the column stands on; a narrower one widens about its centre until the line lands well inside its corner.


def largest_shape(svg: str, names: list[str]) -> Box:
    markups = node_markups(svg)
    shapes = [shape_size(markups[name]) for name in names]
    return Box(0, 0, max(shape.width for shape in shapes), max(shape.height for shape in shapes))


def resized_nodes(svg: str, names: list[str], size: Box) -> str:
    markups = node_markups(svg)
    head = svg[: NODE_TRANSFORM.search(svg).end()]
    return head + "".join(resized_shape(markup, size) if name in names else markup for name, markup in markups.items())
    # The markups run back to back from the end of the first node's transform, so joining them after that head rebuilds the drawing.


def resized_shape(markup: str, size: Box) -> str:
    cylinder = BARE_SHAPE_PATH.search(markup)
    if NODE_RECT.search(markup):
        return NODE_RECT.sub(lambda match: resized_rect(match, size), markup, count=1)
    if cylinder is not None and cylinder["ty"] is not None and CYLINDER_TOP.match(cylinder["d"]):
        return BARE_SHAPE_PATH.sub(lambda match: resized_cylinder(match, size), markup, count=1)
    if STADIUM_OUTLINES.search(markup):
        return STADIUM_OUTLINES.sub(lambda match: resized_stadium(match, size), markup, count=1)
    raise ValueError("only boxes, cylinders, and stadiums can be peers")


def resized_rect(match: re.Match[str], size: Box) -> str:
    center_x, center_y = float(match["x"]) + float(match["width"]) / 2, float(match["y"]) + float(match["height"]) / 2
    return with_groups(match, {"x": f"{center_x - size.width / 2:g}", "y": f"{center_y - size.height / 2:g}", "width": f"{size.width:g}", "height": f"{size.height:g}"})


def resized_cylinder(match: re.Match[str], size: Box) -> str:
    rim = float(CYLINDER_TOP.match(match["d"])["ry"])
    radius, body = size.width / 2, size.height - 2 * rim
    arc = f"a{radius:g},{rim:g} 0,0,0"
    drawn = f"M0,{rim:g} {arc} {2 * radius:g},0 {arc} {-2 * radius:g},0 l0,{body:g} {arc} {2 * radius:g},0 l0,{-body:g}"
    return with_groups(match, {"d": drawn, "tx": f"{-radius:g}", "ty": f"{-(body + 2 * rim) / 2:g}"})
    # Mermaid draws a cylinder from its top-left corner and centres it with its transform, so the new outline is centred the same way and the label keeps its place.


def resized_stadium(match: re.Match[str], size: Box) -> str:
    outline = stadium_outline(size)
    return match["head"] + PATH_DRAWING.sub(lambda _: f'd="{outline}"', match["outlines"])
    # Mermaid draws a stadium as a fill path and a stroke path traced by hand around the node's centre, so both are redrawn as one clean outline about that centre and the label keeps its place.


def stadium_outline(size: Box) -> str:
    radius = size.height / 2
    straight = max(size.width / 2 - radius, 0)
    arc = f"A{radius:g},{radius:g} 0 0 1"
    return f"M{-straight:g},{-radius:g} L{straight:g},{-radius:g} {arc} {straight:g},{radius:g} L{-straight:g},{radius:g} {arc} {-straight:g},{-radius:g} Z"
    # The ends stay fully round: each is a half circle whose radius is half the height, joined by straight top and bottom edges.


def with_groups(match: re.Match[str], values: dict[str, str]) -> str:
    text, offset = match.group(0), match.start()
    for group in sorted(values, key=match.start, reverse=True):
        text = text[: match.start(group) - offset] + values[group] + text[match.end(group) - offset :]
    return text
    # Groups are replaced from the last to the first so the earlier ones keep their positions.


def path_bbox(drawing: str) -> Box:
    points: list[tuple[float, float]] = []
    position = (0.0, 0.0)
    for command, raw in PATH_SEGMENT.findall(drawing):
        position = trace_segment(command, [float(number) for number in NUMBER.findall(raw)], position, points)
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def trace_segment(command: str, numbers: list[float], position: tuple[float, float], points: list[tuple[float, float]]) -> tuple[float, float]:
    x, y = position
    if command in "MLml":
        for index in range(0, len(numbers), 2):
            x, y = numbers[index] + (x if command.islower() else 0), numbers[index + 1] + (y if command.islower() else 0)
            points.append((x, y))
    elif command in "HhVv":
        for number in numbers:
            x, y = (number + (x if command == "h" else 0), y) if command in "Hh" else (x, number + (y if command == "v" else 0))
            points.append((x, y))
    elif command in "Aa":
        for index in range(0, len(numbers), 7):
            rx, ry, level = numbers[index], numbers[index + 1], y
            x, y = numbers[index + 5] + (x if command == "a" else 0), numbers[index + 6] + (y if command == "a" else 0)
            points.extend([(x, y)] + ([(x, y - ry), (x, y + ry)] if level == y else []) + ([(x - rx, y), (x + rx, y)] if position[0] == x else []))
            # A flat arc bulges only up or down by its ry, an upright one only sideways by its rx; both extremes are recorded since the sweep is unknown.
    return (x, y)


def edges_of(svg: str, names: set[str]) -> list[Edge]:
    labels = {match["link"]: Box(0, 0, float(match["width"]), float(match["height"])) for match in EDGE_LABEL.finditer(svg)}
    found = []
    for match in EDGE_PATH.finditer(svg):
        ends = split_link(match["link"], names)
        if ends is not None:
            found.append(Edge(match["link"], ends[0], ends[1], labels.get(match["link"])))
    return found


def split_link(link: str, names: set[str]) -> tuple[str, str] | None:
    parts = link.split("_")
    joins = [("_".join(parts[:index]), "_".join(parts[index:])) for index in range(1, len(parts))]
    return next((join for join in joins if join[0] in names and join[1] in names), None)


def containers_of(source: str) -> list[Container]:
    open_blocks: list[OpenBlock] = []
    found: list[Container] = []
    for line in source.splitlines():
        started = SUBGRAPH.match(line)
        declared = NODE_LINE.match(line)
        if started is not None:
            open_blocks.append(OpenBlock(started["id"], set(), []))
        elif BLOCK_END.match(line) and open_blocks:
            found.append(close_block(open_blocks))
        elif declared is not None and open_blocks:
            open_blocks[-1].members.add(declared["id"])
    return found


def close_block(open_blocks: list[OpenBlock]) -> Container:
    block = open_blocks.pop()
    if open_blocks:
        open_blocks[-1].members.update(block.members)
        open_blocks[-1].children.append(block.id)
    return Container(block.id, frozenset(block.members), tuple(block.children))


def cluster_titles(svg: str) -> dict[str, Title]:
    return {match["id"].split("-")[-1]: title_of(match) for match in CLUSTER.finditer(svg)}


def build_sheet(drawing: Drawing) -> Sheet:
    grid, sizes = drawing.grid, drawing.sizes
    cells = first_cells(grid)
    groups = groups_of(grid)
    spanned = spanned_columns(grid)
    row_spans = spanned_rows(grid)
    entries = entries_of(grid, cells, drawing.edges, drawing.containers, spanned)
    reserved = reserved_cells(grid, drawing.containers)
    extents = {container.id: extent_of(container, cells, reserved[container.id]) for container in drawing.containers}
    strips = {name: drawing.titles[name].natural_height + 2 * TITLE_GAP for name in extents}
    tops = with_entry_room(strips, entries)
    children = {container.id: container.children for container in drawing.containers}
    fan_ins = side_fan_ins(drawing, cells, extents) + column_joins(drawing, cells)
    trunk_room = {fan_in.host: TRUNK_OFFSET for fan_in in fan_ins if fan_in.host is not None}
    across_chrome = chrome({name: (extent[0].column, extent[1].column, 0.0) for name, extent in extents.items()}, children, len(grid[0]), trunk_room)
    down_chrome = chrome({name: (extent[0].row, extent[1].row, tops[name]) for name, extent in extents.items()}, children, len(grid), {})
    columns = spans(with_room_for_titles(cell_sizes(drawing, cells, across=True), drawing.titles, extents), across_chrome, clear_gaps(drawing, cells, across=True))
    rows = spans(cell_sizes(drawing, cells, across=False), down_chrome, clear_gaps(drawing, cells, across=False))
    boxes = {name: centred(columns[cell.column], rows[cell.row], sizes[name]) for name, cell in cells.items()}
    for members in groups.values():
        boxes.update(side_by_side(members, boxes))
    reaches = {name: Span(columns[first].start, columns[last].end - columns[first].start) for name, (first, last) in spanned.items()}
    boxes.update({name: centred(reach, rows[cells[name].row], sizes[name]) for name, reach in reaches.items()})
    boxes.update({name: hung(boxes[name], side) for name, side in drawing.hangs.items()})
    heights = {name: Span(rows[first].start, rows[last].end - rows[first].start) for name, (first, last) in row_spans.items()}
    boxes.update({name: centred(columns[cells[name].column], height, sizes[name]) for name, height in heights.items()})
    cell_rects = {name: Box(columns[cell.column].start, rows[cell.row].start, columns[cell.column].size, rows[cell.row].size) for name, cell in cells.items()}
    cell_rects.update({name: Box(columns[cells[name].column].start, height.start, columns[cells[name].column].size, height.size) for name, height in heights.items()})
    cell_rects.update({name: Box(boxes[name].x, rows[cells[name].row].start, boxes[name].width, rows[cells[name].row].size) for name in grouped_names(groups) | set(drawing.hangs)})
    cell_rects.update({name: Box(reach.start, rows[cells[name].row].start, reach.size, rows[cells[name].row].size) for name, reach in reaches.items()})
    cell_rects = with_room_for_pair_labels(cell_rects, boxes, cells, drawing.edges)
    reserved_rects = {
        container.id: [Box(columns[cell.column].start, rows[cell.row].start, columns[cell.column].size, rows[cell.row].size) for cell in reserved[container.id]] for container in drawing.containers
    }
    trunks_x = {fan_in: trunk_x(columns, across_chrome, fan_in) for fan_in in fan_ins}
    for fan_in in [fan_in for fan_in in fan_ins if fan_in.host is not None]:
        reserved_rects[fan_in.host].append(Box(trunks_x[fan_in], rows[cells[fan_in.legs[0].source].row].start, 0, 0))
    rects = aligned_outlines(container_rects(drawing.containers, cell_rects, reserved_rects, tops), drawing.containers, extents)
    passes = passes_of(grid, cells, unjoined(drawing.edges, cells, drawing.joins), set(drawing.hangs))
    anchors = {name: (size.x + size.width / 2, size.y + size.height / 2) for name, size in sizes.items()}
    sheet = Sheet(
        grid,
        cells,
        columns,
        rows,
        channels(columns, across_chrome),
        channels(rows, down_chrome),
        boxes,
        rects,
        strips,
        {name: drawing.titles[name].natural_width for name in rects},
        anchors,
        drawing.diamonds,
        opposed_pairs(drawing.edges),
        bus_legs_of(drawing.edges, cells),
        {},
        spanned,
        tucked_boxes(grid, cells, drawing.edges, drawing.containers),
        entries,
        {pair: fan_line(columns, across_chrome, cells[pair[0]].column, step) for pair, step in side_fans(grid, cells, drawing.edges).items()},
        {pair: beside_channel(boxes, [pair[0]] + passed_boxes(grid, cells, *pair), side) for pair, side in passes.items()},
        drawing.left_to_right,
        {pair: trunk for fan_in, x in trunks_x.items() for pair, trunk in fan_in_trunks(boxes, fan_in, x, joins_a_straight_line(cells, drawing.edges, fan_in)).items()},
        {},
    )
    return sheet._replace(departures=staggered_departures(sheet, drawing.edges))


def first_cells(grid: list[list[str]]) -> dict[str, Cell]:
    found: dict[str, Cell] = {}
    for row, line in enumerate(grid):
        for column, token in enumerate(line):
            for name in [] if is_empty(token) else token.split(GROUP_JOIN):
                found.setdefault(name, Cell(row, column))
    return found
    # A box written in several cells of one row is placed by its first cell, the one routing reads its column from.


def spanned_columns(grid: list[list[str]]) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    for line in grid:
        for column, token in enumerate(line):
            if not is_empty(token) and GROUP_JOIN not in token and line.count(token) > 1:
                found[token] = (found.get(token, (column, column))[0], column)
    return found
    # A box written in neighbouring cells of one row spans them, centred over the stretch, the way a sketch centres a device above the row of stages it feeds.


def spanned_rows(grid: list[list[str]]) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    for row, line in enumerate(grid):
        for column, token in enumerate(line):
            below = grid[row + 1][column] if row + 1 < len(grid) and column < len(grid[row + 1]) else None
            if is_single_box(token) and token == below:
                found[token] = (found.get(token, (row, row))[0], row + 1)
    return found
    # A box written in the same column of neighbouring rows spans them, centred between them, the way a sketch puts the box feeding a column of services level with the middle of that column.


def side_fans(grid: list[list[str]], cells: dict[str, Cell], edges: list[Edge]) -> dict[tuple[str, str], int]:
    row_spans = spanned_rows(grid)
    beside: dict[tuple[str, int], list[Edge]] = {}
    for edge in edges:
        step = cells[edge.target].column - cells[edge.source].column
        if abs(step) == 1:
            beside.setdefault((edge.source, step), []).append(edge)
    found: dict[tuple[str, str], int] = {}
    for (source, step), legs in beside.items():
        first, last = row_spans.get(source, (cells[source].row, cells[source].row))
        target_rows = [cells[edge.target].row for edge in legs]
        if min(target_rows) < first and max(target_rows) > last:
            found.update({(edge.source, edge.target): step for edge in legs})
    return found
    # A box feeding boxes both above and below it in the next column is drawn as a sketch draws a fan-out: one line out of its side to a trunk in the gap, and a branch from the trunk into the side of each box.
    # A box feeding only the boxes level with it and below keeps its straight line and its elbows.


def fan_line(columns: list[Span], chromes: list[tuple[float, float]], column: int, step: int) -> tuple[float, float]:
    if step > 0:
        return columns[column].end + chromes[column][1] + TRUNK_OFFSET, columns[column + 1].start - chromes[column + 1][0]
    return columns[column].start - chromes[column][0] - TRUNK_OFFSET, columns[column - 1].end + chromes[column - 1][1]
    # The trunk runs just outside the source's column and any container ending there; the branches run on from it to the target column's first border, which bounds the stretch their labels sit in.


def side_fan_ins(drawing: Drawing, cells: dict[str, Cell], extents: dict[str, tuple[Cell, Cell]]) -> list[FanIn]:
    spanned = set(spanned_columns(drawing.grid)) | set(spanned_rows(drawing.grid)) | set(drawing.hangs)
    gathered: dict[tuple[str, int], list[Edge]] = {}
    for edge in [edge for edge in drawing.edges if edge.label is None and not {edge.source, edge.target} & spanned]:
        gathered.setdefault((edge.target, cells[edge.source].column), []).append(edge)
    found = []
    for (target, column), legs in gathered.items():
        if gathers_into_the_side(drawing.grid, cells, legs):
            holders = [container for container in drawing.containers if {leg.source for leg in legs} <= container.members and target not in container.members]
            folders = [container for container in holders if extents[container.id][0].column == extents[container.id][1].column == column]
            hosts = [container for container in holders if extents[container.id][0].column < column == extents[container.id][1].column]
            host = min(hosts, key=lambda container: len(container.members)).id if hosts else None
            found.append(FanIn(target, column, tuple(sorted(legs, key=lambda leg: cells[leg.source].row)), len(folders), host))
    return found
    # Several stored files in one column all read by one box further right, level with the topmost of them or above it, are drawn as a sketch draws a fan-in: each leaves its side into one trunk in the gap, and the trunk enters the target's side.


def column_joins(drawing: Drawing, cells: dict[str, Cell]) -> list[FanIn]:
    found = []
    for target in sorted(drawing.joins):
        legs = [edge for edge in drawing.edges if edge.target == target and is_join_leg(cells, edge)]
        column, members = cells[target].column, {target} | {leg.source for leg in legs}
        hosts = [container for container in drawing.containers if members <= container.members]
        host = min(hosts, key=lambda container: len(container.members)).id if hosts else None
        found.append(FanIn(target, column, tuple(sorted(legs, key=lambda leg: -cells[leg.source].row)), 0, host))
    return found
    # The boxes above a joined box in its column each leave their right side for one trunk just past the column, inside the innermost container holding them all, and the trunk enters the joined box's right side; the nearest box's leg carries the one arrowhead.


def is_join_leg(cells: dict[str, Cell], edge: Edge) -> bool:
    source, target = cells[edge.source], cells[edge.target]
    return edge.label is None and source.column == target.column and source.row < target.row


def unjoined(edges: list[Edge], cells: dict[str, Cell], joins: frozenset[str]) -> list[Edge]:
    return [edge for edge in edges if not (edge.target in joins and is_join_leg(cells, edge))]
    # A join's legs run down their own trunk, so none of them passes beside the boxes in between or widens the joined box to land on it.


def gathers_into_the_side(grid: list[list[str]], cells: dict[str, Cell], legs: list[Edge]) -> bool:
    target, column = cells[legs[0].target], cells[legs[0].source].column
    rows = [cells[leg.source].row for leg in legs]
    across = all(is_empty(grid[target.row][between]) for between in range(column + 1, target.column))
    return len(legs) > 1 and len(set(rows)) == len(rows) and target.column > column and target.row <= min(rows) and across


def trunk_x(columns: list[Span], chromes: list[tuple[float, float]], fan_in: FanIn) -> float:
    if fan_in.host is None:
        return columns[fan_in.column].end + chromes[fan_in.column][1] + TRUNK_OFFSET
    return columns[fan_in.column].end + CONTAINER_PAD * fan_in.folders + TRUNK_OFFSET
    # The trunk runs just outside the containers around the sources' column alone, such as the folder holding the files, and inside the machine around them, which reaches past it.


def joins_a_straight_line(cells: dict[str, Cell], edges: list[Edge], fan_in: FanIn) -> bool:
    target = cells[fan_in.target]
    return target.column != fan_in.column and any(edge.target == fan_in.target and cells[edge.source].row == target.row and cells[edge.source].column < fan_in.column for edge in edges)


def fan_in_trunks(boxes: dict[str, Box], fan_in: FanIn, x: float, joins: bool) -> dict[tuple[str, str], Trunk]:
    levels = [boxes[fan_in.target].center_y] + [boxes[leg.source].center_y for leg in fan_in.legs]
    return {(leg.source, leg.target): Trunk(x, levels[index], index == 0 and not joins) for index, leg in enumerate(fan_in.legs)}
    # Each leg climbs the trunk only as far as the leg above it, so no stretch of the trunk is drawn twice; the topmost reaches the target's row and carries the one arrowhead, unless a straight line into the target's side already passes there and carries it instead.


def passes_of(grid: list[list[str]], cells: dict[str, Cell], edges: list[Edge], hung_boxes: set[str]) -> dict[tuple[str, str], int]:
    found: dict[tuple[str, str], int] = {}
    for edge in [edge for edge in edges if cells[edge.source].column == cells[edge.target].column and not {edge.source, edge.target} & hung_boxes]:
        passed = passed_boxes(grid, cells, edge.source, edge.target)
        if passed:
            found[(edge.source, edge.target)] = quieter_side(cells, edges, {edge.source, edge.target, *passed})
    return found
    # An edge down (or up) a column with a box in between would run straight through that box, so it passes beside it; a box hung under one half already has a stretch of its own beside the box it passes.


def passed_boxes(grid: list[list[str]], cells: dict[str, Cell], source: str, target: str) -> list[str]:
    column, first, last = cells[source].column, min(cells[source].row, cells[target].row), max(cells[source].row, cells[target].row)
    return [name for row in range(first + 1, last) for name in grid[row][column].split(GROUP_JOIN) if not is_empty(grid[row][column])]


def quieter_side(cells: dict[str, Cell], edges: list[Edge], names: set[str]) -> int:
    steps = [outside_step(cells, edge, names) for edge in edges if (edge.source in names) != (edge.target in names)]
    return -1 if sum(step > 0 for step in steps) > sum(step < 0 for step in steps) else 1
    # The line passes on the side of the column fewer other edges reach, the right one when they tie, so it crosses none of them.


def outside_step(cells: dict[str, Cell], edge: Edge, names: set[str]) -> int:
    inside, outside = (edge.source, edge.target) if edge.source in names else (edge.target, edge.source)
    return cells[outside].column - cells[inside].column


def beside_channel(boxes: dict[str, Box], names: list[str], side: int) -> float:
    if side > 0:
        return max(boxes[name].right for name in names) + BESIDE_GAP
    return min(boxes[name].x for name in names) - BESIDE_GAP


def tucked_boxes(grid: list[list[str]], cells: dict[str, Cell], edges: list[Edge], containers: list[Container]) -> frozenset[str]:
    held = {name for container in containers for name in container.members}
    linked = {frozenset((edge.source, edge.target)) for edge in edges}
    fed_from_above = {edge.target for edge in edges if cells[edge.source].row == cells[edge.target].row - 1}
    feeding_above = {edge.source for edge in edges if cells[edge.target].row == cells[edge.source].row - 1}
    detours = fed_from_above & feeding_above - held
    return frozenset(name for name in detours if is_single_box(grid[cells[name].row - 1][cells[name].column]) and frozenset((grid[cells[name].row - 1][cells[name].column], name)) not in linked)
    # A detour hanging under a box it has no edge with, such as a fallback that takes over from the row above and hands back to it; a line into its top would read as coming from the box above.
    # A box that only receives from the row above, such as an outcome several steps drop into, keeps its staircases.


def entries_of(grid: list[list[str]], cells: dict[str, Cell], edges: list[Edge], containers: list[Container], spanned: dict[str, tuple[int, int]]) -> dict[tuple[str, str], tuple[str, ...]]:
    linked = {frozenset((edge.source, edge.target)) for edge in edges}
    fans = side_fans(grid, cells, edges)
    found: dict[tuple[str, str], tuple[str, ...]] = {}
    for edge in [edge for edge in edges if not {edge.source, edge.target} & set(spanned) and (edge.source, edge.target) not in fans]:
        upper, lower = sorted((edge.source, edge.target), key=lambda name: cells[name].row)
        entered = sorted((container for container in containers if lower in container.members and upper not in container.members), key=lambda container: -len(container.members))
        if entered and hangs_over_a_stranger(grid, cells, linked, upper, lower):
            found[(edge.source, edge.target)] = tuple(container.id for container in entered)
    return found
    # The containers an edge enters are listed from the outermost in, so the last is the one its turn is drawn inside.


def hangs_over_a_stranger(grid: list[list[str]], cells: dict[str, Cell], linked: set[frozenset[str]], upper: str, lower: str) -> bool:
    above, below = cells[upper], cells[lower]
    beneath = grid[below.row][above.column]
    return below.row == above.row + 1 and above.column != below.column and is_single_box(beneath) and frozenset((upper, beneath)) not in linked
    # A device above a machine, hanging over a box it has no edge with and feeding boxes beside it, as a puck hangs over the intent matcher and feeds the stages either side.


def with_entry_room(strips: dict[str, float], entries: dict[tuple[str, str], tuple[str, ...]]) -> dict[str, float]:
    innermost = {entered[-1] for entered in entries.values()}
    return {name: strip + (ENTRY_ROOM if name in innermost else 0.0) for name, strip in strips.items()}
    # The room sits between the container's title and its top row, where an edge entering from above turns, clear of the title.


def with_room_for_pair_labels(cell_rects: dict[str, Box], boxes: dict[str, Box], cells: dict[str, Cell], edges: list[Edge]) -> dict[str, Box]:
    shifts = opposed_pairs(edges)
    widened = dict(cell_rects)
    for edge in [edge for edge in edges if edge.label is not None and (edge.source, edge.target) in shifts and cells[edge.source].column == cells[edge.target].column]:
        lower = max(edge.source, edge.target, key=lambda name: cells[name].row)
        line_x = shared_middle(boxes[edge.source], boxes[edge.target]) + shifts[(edge.source, edge.target)]
        widened[lower] = bounds([widened[lower], pair_label_reach(line_x, shifts[(edge.source, edge.target)], edge.label.width, widened[lower].y)])
    return widened
    # A vertical pair's labels sit outside its lines, beside the box below; the containers around that box reach far enough to keep each label as clear of their border as of its own line.


def pair_label_reach(line_x: float, shift: float, label_width: float, y: float) -> Box:
    outward = 1 if shift > 0 else -1
    return Box(line_x + outward * (2 * LABEL_CLEARANCE + label_width - CONTAINER_PAD), y, 0, 0)
    # The container's padding already holds part of the clearance beyond the label, so only the rest widens what it wraps.


def hung(box: Box, side: int) -> Box:
    return box._replace(x=box.x + side * box.width / 2)
    # Half its own width to one side puts the box's inner edge on its column's centre line, under one half of the box above.


def is_single_box(token: str) -> bool:
    return not is_empty(token) and GROUP_JOIN not in token


def groups_of(grid: list[list[str]]) -> dict[str, tuple[str, ...]]:
    return {token: tuple(token.split(GROUP_JOIN)) for line in grid for token in line if GROUP_JOIN in token}


def grouped_names(groups: dict[str, tuple[str, ...]]) -> set[str]:
    return {name for members in groups.values() for name in members}


def side_by_side(members: tuple[str, ...], boxes: dict[str, Box]) -> dict[str, Box]:
    placed: dict[str, Box] = {}
    total_width = sum(boxes[name].width for name in members) + GROUP_GAP * (len(members) - 1)
    left = boxes[members[0]].center_x - total_width / 2
    for name in members:
        placed[name] = boxes[name]._replace(x=left)
        left += boxes[name].width + GROUP_GAP
    return placed
    # The group is spread out from the cell's centre with a gap narrower than a column's, so its members read as hanging under the one box above them.


def opposed_pairs(edges: list[Edge]) -> dict[tuple[str, str], float]:
    ends = [(edge.source, edge.target) for edge in edges]
    return {pair: -OPPOSING_OFFSET if ends.index(pair) < ends.index(pair[::-1]) else OPPOSING_OFFSET for pair in ends if pair[::-1] in ends}
    # The edge written first takes the line above the centre (or left of it), the other the line below (or right of it): a sketch that draws each side box's request above its reply keeps that order on both sides of the column.


def bus_legs_of(edges: list[Edge], cells: dict[str, Cell]) -> frozenset[tuple[str, str]]:
    between_rows = [edge for edge in edges if edge.label is None and cells[edge.target].row != cells[edge.source].row]
    counts = Counter((edge.source, cells[edge.target].row) for edge in between_rows)
    return frozenset((edge.source, edge.target) for edge in between_rows if counts[(edge.source, cells[edge.target].row)] > 1)
    # A box sending several unlabelled edges into one row, below it or above it, is drawn as a sketch draws a bus: every leg leaves its centre, they share one line across the gutter next to it, and each enters the centre of its target.
    # A labelled edge keeps a line of its own, so its label never sits on a trunk it shares with another edge.


def is_empty(token: str) -> bool:
    return token.startswith(EMPTY_CELL)


def reserved_cells(grid: list[list[str]], containers: list[Container]) -> dict[str, list[Cell]]:
    named = {container.id: [Cell(row, column) for row, line in enumerate(grid) for column, token in enumerate(line) if token == EMPTY_CELL + container.id] for container in containers}
    for container in containers:
        named[container.id] += [cell for child in container.children for cell in named[child]]
    return named
    # A container lists its children before it closes, so each child's reserved cells are complete by the time its parent collects them.


def extent_of(container: Container, cells: dict[str, Cell], reserved: list[Cell]) -> tuple[Cell, Cell]:
    inside = [cells[name] for name in container.members if name in cells] + reserved
    return Cell(min(cell.row for cell in inside), min(cell.column for cell in inside)), Cell(max(cell.row for cell in inside), max(cell.column for cell in inside))


def with_room_for_titles(widths: list[float], titles: dict[str, Title], extents: dict[str, tuple[Cell, Cell]]) -> list[float]:
    widened = list(widths)
    for name, (first, last) in extents.items():
        if first.column == last.column:
            widened[first.column] = max(widened[first.column], column_width_for_title(titles[name]))
    return widened
    # A container one column wide is as wide as its boxes, and a title longer than them would wrap; its column grows until the title fits on one line.


def column_width_for_title(title: Title) -> float:
    return title.natural_width + 2 * TITLE_INSET - 2 * CONTAINER_PAD


def cell_sizes(drawing: Drawing, cells: dict[str, Cell], across: bool) -> list[float]:
    lines = range(len(drawing.grid[0]) if across else len(drawing.grid))
    grouped = grouped_names(groups_of(drawing.grid)) | set(spanned_columns(drawing.grid)) if across else set(spanned_rows(drawing.grid))
    sized = {name: cell for name, cell in cells.items() if name not in grouped}
    measured = [[drawing.sizes[name].width if across else drawing.sizes[name].height for name, cell in sized.items() if (cell.column if across else cell.row) == line] for line in lines]
    return [max(line, default=0.0) for line in measured]
    # A group's width does not size its column: it reaches into the empty cells beside it instead of pushing the row above apart.


def chrome(reaches: dict[str, tuple[int, int, float]], children: dict[str, tuple[str, ...]], count: int, trailing: dict[str, float]) -> list[tuple[float, float]]:
    before = deepest_stacks({name: (first, CONTAINER_PAD + strip) for name, (first, _, strip) in reaches.items()}, children, count)
    after = deepest_stacks({name: (last, CONTAINER_PAD + trailing.get(name, 0.0)) for name, (_, last, _) in reaches.items()}, children, count)
    return list(zip(before, after))
    # A container holding a fan-in's trunk past its last column reaches that much further, and the gap beyond it moves over with it.


def deepest_stacks(borders: dict[str, tuple[int, float]], children: dict[str, tuple[str, ...]], count: int) -> list[float]:
    return [max((stack_depth(name, borders, children) for name, (line, _) in borders.items() if line == at), default=0.0) for at in range(count)]
    # Containers side by side whose borders fall on one line share that line's room; only containers nested in one another stack their padding and title strips.


def stack_depth(name: str, borders: dict[str, tuple[int, float]], children: dict[str, tuple[str, ...]]) -> float:
    line, thickness = borders[name]
    return thickness + max((stack_depth(child, borders, children) for child in children[name] if borders[child][0] == line), default=0.0)


def clear_gaps(drawing: Drawing, cells: dict[str, Cell], across: bool) -> list[float]:
    count = len(drawing.grid[0]) if across else len(drawing.grid)
    base = drawing.column_gap if across else ROW_GAP
    lane_room = {} if across else drawing.lane_room
    fan_room = fan_label_room(drawing, cells) if across else {}
    gaps = [MARGIN if line in (0, count) else max(base, neighbour_label(drawing.edges, cells, line, across), lane_room.get(line, 0.0), fan_room.get(line, 0.0)) for line in range(count + 1)]
    return evened_between_peers(gaps, [[cells[name].column if across else cells[name].row for name in names] for names in drawing.peers])


def fan_label_room(drawing: Drawing, cells: dict[str, Cell]) -> dict[int, float]:
    fans = side_fans(drawing.grid, cells, drawing.edges)
    room: dict[int, float] = {}
    for edge in [edge for edge in drawing.edges if (edge.source, edge.target) in fans and edge.label is not None]:
        line = max(cells[edge.source].column, cells[edge.target].column)
        room[line] = max(room.get(line, 0.0), TRUNK_OFFSET + edge.label.width + 2 * LABEL_CLEARANCE)
    return room
    # A fan's labels sit on its branches between the trunk and the target column's border, so the gap holds the trunk's offset and the widest label with its clearance.


def evened_between_peers(gaps: list[float], peer_lines: list[list[int]]) -> list[float]:
    evened = list(gaps)
    for lines in peer_lines:
        between = range(min(lines) + 1, max(lines) + 1)
        widest = max((evened[line] for line in between), default=0.0)
        evened[between.start : between.stop] = [widest] * len(between)
    return evened
    # A gap is widened only to the widest gap already between the same peers, so peers in one row or one column stand evenly apart.


def neighbour_label(edges: list[Edge], cells: dict[str, Cell], line: int, across: bool) -> float:
    spanned = [edge for edge in edges if edge.label is not None and spans_gap(cells[edge.source], cells[edge.target], line, across)]
    return max([edge.label.width if across else edge.label.height for edge in spanned] + [0.0]) + 2 * LABEL_CLEARANCE


def spans_gap(source: Cell, target: Cell, line: int, across: bool) -> bool:
    along = (source.column, target.column) if across else (source.row, target.row)
    other = (source.row, target.row) if across else (source.column, target.column)
    return other[0] == other[1] and abs(along[0] - along[1]) == 1 and max(along) == line


def spans(sizes: list[float], chromes: list[tuple[float, float]], gaps: list[float]) -> list[Span]:
    found: list[Span] = []
    cursor = 0.0
    for line, size in enumerate(sizes):
        cursor += gaps[line] + chromes[line][0] + (chromes[line - 1][1] if line else 0)
        found.append(Span(cursor, size))
        cursor += size
    return found


def channels(lines: list[Span], chromes: list[tuple[float, float]]) -> list[float]:
    clear = [(lines[index - 1].end + chromes[index - 1][1], lines[index].start - chromes[index][0]) for index in range(1, len(lines))]
    return [lines[0].start - chromes[0][0] - MARGIN / 2] + [(first + second) / 2 for first, second in clear] + [lines[-1].end + chromes[-1][1] + MARGIN / 2]
    # A line that has to pass a row runs down the middle of the clear part of a gap, never along a container's border.


def centred(column: Span, row: Span, size: Box) -> Box:
    return Box(column.center - size.width / 2, row.center - size.height / 2, size.width, size.height)


def container_rects(containers: list[Container], cell_rects: dict[str, Box], reserved_rects: dict[str, list[Box]], strips: dict[str, float]) -> dict[str, Box]:
    rects: dict[str, Box] = {}
    for container in containers:
        held = [cell_rects[name] for name in container.members if name in cell_rects] + [rects[child] for child in container.children] + reserved_rects[container.id]
        rects[container.id] = padded(bounds(held), strips[container.id])
    return rects


def aligned_outlines(rects: dict[str, Box], containers: list[Container], extents: dict[str, tuple[Cell, Cell]]) -> dict[str, Box]:
    nested = {child for container in containers for child in container.children}
    top_level = [container.id for container in containers if container.id not in nested]
    aligned = dict(rects)
    for name in top_level:
        top = min(rects[other].y for other in top_level if extents[other][0].row == extents[name][0].row)
        bottom = max(rects[other].bottom for other in top_level if extents[other][1].row == extents[name][1].row)
        aligned[name] = Box(rects[name].x, top, rects[name].width, bottom - top)
    return aligned
    # Two machines side by side are one row of places, so their outlines and titles line up even when one holds a nested container whose own title strip and padding push it further out.


def bounds(boxes: list[Box]) -> Box:
    left, top = min(box.x for box in boxes), min(box.y for box in boxes)
    return Box(left, top, max(box.right for box in boxes) - left, max(box.bottom for box in boxes) - top)


def padded(box: Box, strip: float) -> Box:
    return Box(box.x - CONTAINER_PAD, box.y - CONTAINER_PAD - strip, box.width + 2 * CONTAINER_PAD, box.height + 2 * CONTAINER_PAD + strip)


def route_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    start, end = sheet.cells[source], sheet.cells[target]
    if (source, target) in sheet.fans:
        return fan_points(sheet, source, target)
    if (source, target) in sheet.trunks:
        return fan_in_points(sheet, source, target)
    if (source, target) in sheet.entries:
        return entry_points(sheet, source, target)
    if is_tucked_elbow(sheet, source, target):
        return tucked_elbow_points(sheet, source, target)
    if (source, target) in sheet.passes:
        return passing_points(sheet, source, target)
    if returns_by_the_right(sheet, source, target):
        return right_return_points(sheet, source, target)
    if start.row == end.row:
        return same_row_points(sheet, source, target)
    if start.column == end.column:
        return same_column_points(sheet, source, target)
    return staircase_points(sheet, source, target)


def fan_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    trunk, _ = sheet.fans[(source, target)]
    source_box, target_box = sheet.boxes[source], sheet.boxes[target]
    rightward = trunk > source_box.center_x
    leaving, arriving = (source_box.right, target_box.x - ARROW_GAP) if rightward else (source_box.x, target_box.right + ARROW_GAP)
    if abs(target_box.center_y - source_box.center_y) < SAME_LINE_TOLERANCE:
        return [(leaving, source_box.center_y), (arriving, target_box.center_y)]
    return [(leaving, source_box.center_y), (trunk, source_box.center_y), (trunk, target_box.center_y), (arriving, target_box.center_y)]


def fan_in_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    trunk, source_box = sheet.trunks[(source, target)], sheet.boxes[source]
    target_box = sheet.boxes[target]
    arriving_x = target_box.right + ARROW_GAP if trunk.x > target_box.center_x else target_box.x - ARROW_GAP
    ending = [(arriving_x, trunk.join_y)] if trunk.lands else []
    if abs(source_box.center_y - trunk.join_y) < SAME_LINE_TOLERANCE:
        return [(source_box.right, trunk.join_y)] + (ending or [(trunk.x, trunk.join_y)])
    return [(source_box.right, source_box.center_y), (trunk.x, source_box.center_y), (trunk.x, trunk.join_y)] + ending


def passing_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    channel, source_box, target_box = sheet.passes[(source, target)], sheet.boxes[source], sheet.boxes[target]
    leaving = source_box.right if channel > source_box.center_x else source_box.x
    arriving = target_box.y - ARROW_GAP if target_box.center_y > source_box.center_y else target_box.bottom + ARROW_GAP
    return [(leaving, source_box.center_y), (channel, source_box.center_y), (channel, arriving)]
    # Out of the source's side, down past the boxes in between, and into the top of the box below, which is wide enough to catch it.


def entry_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    level = entry_level(sheet, source, target)
    if sheet.cells[target].row > sheet.cells[source].row:
        leaving, arriving = attachment_x(sheet, source, target), sheet.boxes[target].center_x
        return [(leaving, leaving_y(sheet, source, leaving, descending=True)), (leaving, level), (arriving, level), (arriving, arriving_y(sheet, target, arriving, descending=True))]
    leaving, arriving = sheet.boxes[source].center_x, attachment_x(sheet, target, source)
    return [(leaving, leaving_y(sheet, source, leaving, descending=False)), (leaving, level), (arriving, level), (arriving, arriving_y(sheet, target, arriving, descending=False))]
    # The line crosses the container tops straight under the device, turns inside the innermost one below its title, and meets the box inside in the centre of its top.


def entry_level(sheet: Sheet, source: str, target: str) -> float:
    innermost = sheet.entries[(source, target)][-1]
    lower = max(source, target, key=lambda name: sheet.cells[name].row)
    title_bottom = sheet.containers[innermost].y + sheet.strips[innermost] - TITLE_GAP
    return (title_bottom + sheet.rows[sheet.cells[lower].row].start) / 2


def entry_label_stretch(sheet: Sheet, edge: Edge, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    outer_top = sheet.containers[sheet.entries[(edge.source, edge.target)][0]].y
    if sheet.cells[edge.target].row > sheet.cells[edge.source].row:
        return [points[0], (points[0][0], outer_top)]
    return [(points[-1][0], outer_top + ARROW_GAP), points[-1]]
    # The label sits beside the stretch between the device and the outermost container, outside every machine, as a sketch writes it.


def returns_by_the_right(sheet: Sheet, source: str, target: str) -> bool:
    start, end = sheet.cells[source], sheet.cells[target]
    if not (end.row < start.row and end.column < start.column) or (source, target) in sheet.bus_legs:
        return False
    beyond = range(start.column + 1, len(sheet.grid[0]))
    beside_is_clear = all(is_empty(sheet.grid[row][column]) for row in range(end.row, start.row + 1) for column in beyond)
    return beside_is_clear and all(is_empty(sheet.grid[end.row][column]) for column in range(end.column + 1, start.column + 1))
    # A result fed back up into an earlier box, with nothing to the right of the loop, is drawn the way a sketch draws it: out of the source's right side, up, and into the target's right side.
    # A leg of a bus rising into the row above stays on the bus's trunk instead.


def right_return_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    source_box, target_box = sheet.boxes[source], sheet.boxes[target]
    column = sheet.cells[source].column
    channel = max(sheet.channels_x[column + 1], sheet.columns[column].end + COLUMN_GAP / 2)
    return [(source_box.right, source_box.center_y), (channel, source_box.center_y), (channel, target_box.center_y), (target_box.right + ARROW_GAP, target_box.center_y)]


def same_row_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    source_box, target_box = sheet.boxes[source], sheet.boxes[target]
    shift = opposing_shift(sheet, source, target)
    if sheet.cells[target].column > sheet.cells[source].column:
        return [(source_box.right, source_box.center_y + shift), (target_box.x - ARROW_GAP, target_box.center_y + shift)]
    if row_is_clear(sheet, sheet.cells[source], sheet.cells[target]):
        return [(source_box.x, source_box.center_y + shift), (target_box.right + ARROW_GAP, target_box.center_y + shift)]
    gutter = sheet.channels_y[sheet.cells[source].row + 1]
    leaving, arriving = attachment_x(sheet, source, target), attachment_x(sheet, target, source)
    return [(leaving, leaving_y(sheet, source, leaving, descending=True)), (leaving, gutter), (arriving, gutter), (arriving, arriving_y(sheet, target, arriving, descending=False))]


def opposing_shift(sheet: Sheet, source: str, target: str) -> float:
    return sheet.opposed.get((source, target), 0.0)
    # Two neighbours that send each other something would share one straight line; one edge moves up (or left) and the other down (or right), so both stay readable.


def same_column_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    descending = sheet.cells[target].row > sheet.cells[source].row
    x = shared_middle(sheet.boxes[source], sheet.boxes[target]) + opposing_shift(sheet, source, target)
    return [(x, leaving_y(sheet, source, x, descending)), (x, arriving_y(sheet, target, x, descending))]


def shared_middle(first: Box, second: Box) -> float:
    return (max(first.x, second.x) + min(first.right, second.right)) / 2
    # The line drops through the middle of the stretch both boxes share: their common centre for two boxes centred in one column, and a leg off to one side for a member of a group or a box hung under one half.


def staircase_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    start, end = sheet.cells[source], sheet.cells[target]
    if elbow_is_clear(sheet, start, end):
        return elbow_points(sheet, source, target)
    if (source, target) not in sheet.bus_legs and rise_is_clear(sheet, start, end):
        return rise_points(sheet, source, target)
    if (source, target) in sheet.lanes:
        return laned_points(sheet, source, target)
    descending = end.row > start.row
    leaving, arriving = departure_x(sheet, source, target), arrival_x(sheet, source, target)
    first = sheet.channels_y[start.row + 1 if descending else start.row]
    ends = [(leaving, leaving_y(sheet, source, leaving, descending)), (arriving, arriving_y(sheet, target, arriving, descending))]
    if column_is_clear(sheet, end.column, start.row, end.row):
        return [ends[0], (leaving, first), (arriving, first), ends[1]]
    last = sheet.channels_y[end.row if descending else end.row + 1]
    channel = sheet.channels_x[end.column + 1 if end.column < start.column else end.column]
    return [ends[0], (leaving, first), (channel, first), (channel, last), (arriving, last), ends[1]]


def laned_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    lane, descending = sheet.lanes[(source, target)], sheet.cells[target].row > sheet.cells[source].row
    leaving, arriving = (lane.departure_x, leaving_y(sheet, source, lane.departure_x, descending)), (lane.arrival_x, arriving_y(sheet, target, lane.arrival_x, descending))
    return [leaving, (lane.departure_x, lane.level), (lane.arrival_x, lane.level), arriving]


def is_tucked_elbow(sheet: Sheet, source: str, target: str) -> bool:
    start, end = sheet.cells[source], sheet.cells[target]
    if abs(end.row - start.row) != 1 or start.column == end.column or source in sheet.spanned or target in sheet.spanned:
        return False
    lower, upper = (target, source) if end.row > start.row else (source, target)
    corner = Cell(sheet.cells[lower].row, sheet.cells[upper].column)
    return lower in sheet.tucked and is_empty(sheet.grid[corner.row][corner.column])


def tucked_elbow_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    source_box, target_box = sheet.boxes[source], sheet.boxes[target]
    if sheet.cells[target].row > sheet.cells[source].row:
        side = target_box.x - ARROW_GAP if target_box.center_x > source_box.center_x else target_box.right + ARROW_GAP
        return [(source_box.center_x, source_box.bottom), (source_box.center_x, target_box.center_y), (side, target_box.center_y)]
    side = source_box.right if target_box.center_x > source_box.center_x else source_box.x
    return [(side, source_box.center_y), (target_box.center_x, source_box.center_y), (target_box.center_x, target_box.bottom + ARROW_GAP)]
    # A tucked box is reached down the other box's centre line and into its side, and left by its side and up into the other box's centre, so no line touches its top under the box it hangs from.


def elbow_is_clear(sheet: Sheet, start: Cell, end: Cell) -> bool:
    if end.row <= start.row or not leaves_by_the_side(sheet, start, end):
        return False
    below = all(is_empty(sheet.grid[row][start.column]) for row in range(start.row + 1, end.row + 1))
    across = all(is_empty(sheet.grid[end.row][column]) for column in range(min(start.column, end.column) + 1, max(start.column, end.column)))
    return below and across


def leaves_by_the_side(sheet: Sheet, start: Cell, end: Cell) -> bool:
    corner = Cell(end.row, start.column)
    around_start, around_corner, around_end = (containers_holding(sheet, cell) for cell in (start, corner, end))
    enters_from_outside = not around_start and not around_corner and bool(around_end)
    in_the_open = sheet.left_to_right and not (around_start or around_corner or around_end)
    return enters_from_outside or in_the_open or any(name in around_corner and name not in around_end for name in around_start)
    # As in a sketch, the edge runs down and into the target's side when the source's container reaches the target's row or the source is in none; one leaving a container's bottom keeps the staircase.
    # In a left-to-right figure the same holds outside every container: a later step one row down is reached by its side, as time runs across.


def rise_is_clear(sheet: Sheet, start: Cell, end: Cell) -> bool:
    if not sheet.left_to_right or end.row >= start.row or start.column == end.column:
        return False
    step = 1 if end.column > start.column else -1
    across = all(is_empty(sheet.grid[start.row][column]) for column in range(start.column + step, end.column + step, step))
    up = all(is_empty(sheet.grid[row][end.column]) for row in range(end.row + 1, start.row))
    return across and up and not any(containers_holding(sheet, cell) for cell in (start, Cell(start.row, end.column), end))
    # In a left-to-right figure, outside every container, an edge up to a box in a later column runs as a sketch draws it: out of the source's side, along its row under the boxes in between, and up into the target's bottom.


def rise_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    source_box, target_box = sheet.boxes[source], sheet.boxes[target]
    leaving = source_box.right if target_box.center_x > source_box.center_x else source_box.x
    return [(leaving, source_box.center_y), (target_box.center_x, source_box.center_y), (target_box.center_x, target_box.bottom + ARROW_GAP)]


def is_rise(sheet: Sheet, source: str, target: str) -> bool:
    start, end = sheet.cells[source], sheet.cells[target]
    return start.column != end.column and (source, target) not in sheet.fans and route_points(sheet, source, target) == rise_points(sheet, source, target)


def containers_holding(sheet: Sheet, cell: Cell) -> set[str]:
    return {name for name, rect in sheet.containers.items() if extent_holds(rect, sheet, cell)}


def extent_holds(rect: Box, sheet: Sheet, cell: Cell) -> bool:
    column, row = sheet.columns[cell.column], sheet.rows[cell.row]
    return rect.x <= column.center <= rect.right and rect.y <= row.center <= rect.bottom


def elbow_points(sheet: Sheet, source: str, target: str) -> list[tuple[float, float]]:
    source_box, target_box = sheet.boxes[source], sheet.boxes[target]
    leaving = sheet.departures.get((source, target), departure_x(sheet, source, target))
    side = target_box.x - ARROW_GAP if sheet.cells[target].column > sheet.cells[source].column else target_box.right + ARROW_GAP
    return [(leaving, leaving_y(sheet, source, leaving, descending=True)), (leaving, target_box.center_y), (side, target_box.center_y)]
    # An edge that leaves one container for a box lower down in another is drawn the way a sketch draws it: straight down out of the source, then across into the target's side, crossing each border once.


def staggered_departures(sheet: Sheet, edges: list[Edge]) -> dict[tuple[str, str], float]:
    elbows: dict[tuple[str, int], list[Edge]] = {}
    for edge in [edge for edge in edges if is_elbow(sheet, edge.source, edge.target)]:
        elbows.setdefault((edge.source, facing_side(sheet, edge.source, edge.target)), []).append(edge)
    found: dict[tuple[str, str], float] = {}
    for (source, side), legs in elbows.items():
        rows = [sheet.cells[leg.target].row for leg in legs]
        if len(legs) > 1 and len(set(rows)) == len(rows):
            found.update(stepped_departures(sheet.boxes[source], side, sorted(legs, key=lambda leg: sheet.cells[leg.target].row)))
    return found
    # Two elbows out of one box toward one side would share their drop until the nearer one turns off; each leaves at its own point instead, as a sketch draws a pass and a fail branching from one test.


def is_elbow(sheet: Sheet, source: str, target: str) -> bool:
    start, end = sheet.cells[source], sheet.cells[target]
    return start.column != end.column and start.row != end.row and route_points(sheet, source, target) == elbow_points(sheet, source, target)


def facing_side(sheet: Sheet, source: str, target: str) -> int:
    return 1 if sheet.cells[target].column > sheet.cells[source].column else -1


def stepped_departures(box: Box, side: int, nearest_first: list[Edge]) -> dict[tuple[str, str], float]:
    last = len(nearest_first) - 1
    return {(leg.source, leg.target): box.center_x + side * box.width * ATTACHMENT_FRACTION * (1 - 2 * index / last) for index, leg in enumerate(nearest_first)}
    # The departures spread evenly from a quarter of the width toward the targets to a quarter away from them, the nearest row's the closest to the targets, so each farther line drops outside the nearer ones and runs under their corners without crossing them.


def staggered_label_stretch(sheet: Sheet, edge: Edge, edges: list[Edge], routes: dict[str, list[tuple[float, float]]]) -> list[tuple[float, float]]:
    (x, leaving), (_, turn) = routes[edge.link][:2]
    siblings = [other for other in edges if other.source == edge.source and other.link != edge.link and (other.source, other.target) in sheet.departures]
    higher_turns = [routes[other.link][1][1] for other in siblings if routes[other.link][1][1] < turn]
    return [(x, max(higher_turns, default=leaving)), (x, turn)]
    # A farther branch's label sits on its drop below the nearer branch's turn, so it is read beside its own line alone.


def leaving_y(sheet: Sheet, node: str, x: float, descending: bool) -> float:
    box, inset = sheet.boxes[node], diamond_inset(sheet, node, x)
    return box.bottom - inset if descending else box.y + inset


def arriving_y(sheet: Sheet, node: str, x: float, descending: bool) -> float:
    box, inset = sheet.boxes[node], diamond_inset(sheet, node, x)
    return box.y + inset - ARROW_GAP if descending else box.bottom - inset + ARROW_GAP


def diamond_inset(sheet: Sheet, node: str, x: float) -> float:
    box = sheet.boxes[node]
    if node not in sheet.diamonds or box.width == 0:
        return 0.0
    return (box.height / 2) * min(1.0, abs(x - box.center_x) / (box.width / 2))
    # A rhombus's outline at a horizontal offset from its apex sits above the bounding box's bottom by a proportional inset; without it an offset edge starts in whitespace.


def row_is_clear(sheet: Sheet, source: Cell, target: Cell) -> bool:
    between = range(min(source.column, target.column) + 1, max(source.column, target.column))
    return all(is_empty(sheet.grid[source.row][column]) for column in between)


def column_is_clear(sheet: Sheet, column: int, first_row: int, second_row: int) -> bool:
    between = range(min(first_row, second_row) + 1, max(first_row, second_row))
    return all(is_empty(sheet.grid[row][column]) for row in between)


def departure_x(sheet: Sheet, source: str, target: str) -> float:
    if (source, target) in sheet.bus_legs or target in sheet.spanned:
        return sheet.boxes[source].center_x
    return attachment_x(sheet, source, target)


def arrival_x(sheet: Sheet, source: str, target: str) -> float:
    if (source, target) in sheet.bus_legs or source in sheet.spanned:
        return sheet.boxes[target].center_x
    return attachment_x(sheet, target, source)
    # A spanning box's edges land in the centre of the box at their other end, as a bus's legs do; only on the spanning box itself are they spread to the side facing that box.


def attachment_x(sheet: Sheet, node: str, other: str) -> float:
    box, cell, other_cell = sheet.boxes[node], sheet.cells[node], sheet.cells[other]
    if cell.column == other_cell.column:
        return box.center_x
    side = -1 if other_cell.column < cell.column else 1
    return box.center_x + side * box.width * ATTACHMENT_FRACTION


def laned_sheet(drawing: Drawing) -> Sheet:
    sheet = build_sheet(drawing)
    crowded = crowded_gutters(sheet, drawing.edges)
    fanned = {gutter: runs for gutter, runs in fan_in_gutters(sheet, drawing.edges).items() if gutter not in crowded}
    hubbed = hub_gutters(sheet, drawing.edges)
    if not crowded and not fanned and not hubbed:
        return sheet
    room = {gutter: lane_room(sheet, drawing.edges, gutter, len(runs)) for gutter, runs in crowded.items()} | {gutter: lane_room(sheet, drawing.edges, gutter, 1) for gutter in fanned}
    room |= {gutter: ROW_GAP + max(edge.label.height + 2 * LABEL_CLEARANCE for edge in runs) - ROW_GAP / 2 for gutter, runs in hubbed.items()}
    roomy = build_sheet(drawing._replace(lane_room=room))
    lanes = {key: lane for gutter, runs in crowded.items() for key, lane in fewest_crossings(roomy, drawing.edges, lane_choices(roomy, drawing.edges, gutter, runs)).items()}
    lanes |= {key: lane for gutter, runs in fanned.items() for key, lane in fan_in_lanes(roomy, drawing.edges, gutter, runs).items()}
    return roomy._replace(lanes=lanes | {key: lane for gutter, runs in hubbed.items() for key, lane in hub_lanes(roomy, runs, room[gutter]).items()})
    # The gutter is first measured as if nothing ran along another edge's line; only where something does, where labelled edges converge on one box, or where a spanning box's labelled edges cross it, is its row gap grown.


def hub_gutters(sheet: Sheet, edges: list[Edge]) -> dict[int, list[Edge]]:
    runs: dict[int, list[Edge]] = {}
    for edge in [edge for edge in edges if is_hub_edge(sheet, edge) and edge.label is not None]:
        runs.setdefault(max(sheet.cells[edge.source].row, sheet.cells[edge.target].row), []).append(edge)
    return runs


def is_hub_edge(sheet: Sheet, edge: Edge) -> bool:
    start, end = sheet.cells[edge.source], sheet.cells[edge.target]
    return (edge.source in sheet.spanned) != (edge.target in sheet.spanned) and abs(end.row - start.row) == 1


def hub_lanes(sheet: Sheet, runs: list[Edge], room: float) -> dict[tuple[str, str], Lane]:
    lanes: dict[tuple[str, str], Lane] = {}
    for edge in runs:
        hub = edge.source if edge.source in sheet.spanned else edge.target
        other = edge.target if hub == edge.source else edge.source
        toward_hub = -1 if sheet.cells[hub].row < sheet.cells[other].row else 1
        level = sheet.channels_y[max(sheet.cells[hub].row, sheet.cells[other].row)] + toward_hub * (room - ROW_GAP) / 2
        lanes[(edge.source, edge.target)] = Lane(departure_x(sheet, edge.source, edge.target), arrival_x(sheet, edge.source, edge.target), level)
    return lanes
    # The runs cross the gutter half a row gap from the spanning box, leaving a band beside the other box for each label, next to the leg that reaches that box.
    # The gutter is first measured as if nothing ran along another edge's line; only where something does, or where labelled edges converge on one box, is its row gap grown.


def fan_in_edges(cells: dict[str, Cell], edges: list[Edge]) -> list[Edge]:
    dropping = [edge for edge in edges if edge.label is not None and cells[edge.target].row == cells[edge.source].row + 1]
    sources = Counter(target for _, target in {(edge.source, edge.target) for edge in dropping})
    return [edge for edge in dropping if sources[edge.target] > 1]
    # Labelled edges from several boxes of one row converging on one box in the row below, such as the steps of a chain each saving a key to one file.


def fan_in_gutters(sheet: Sheet, edges: list[Edge]) -> dict[int, list[Edge]]:
    routes = {edge.link: route_points(sheet, edge.source, edge.target) for edge in edges}
    placed = placed_labels(sheet, edges, routes, title_x_positions(sheet, routes))
    converging = fan_in_edges(sheet.cells, edges)
    stranded_rows = {sheet.cells[edge.target].row for edge in converging if not placed[edge.link][1]}
    runs: dict[int, list[Edge]] = {}
    for edge in [edge for edge in converging if is_gutter_run(sheet, routes[edge.link])]:
        runs.setdefault(sheet.channels_y.index(routes[edge.link][1][1]), []).append(edge)
    return {gutter: members for gutter, members in runs.items() if gutter in stranded_rows}
    # Converging edges usually keep their labels on their own lines; only when one of those labels has no clear spot, because the turns run along one line side by side, does the gutter get a shared level and a label band.


def fan_in_lanes(sheet: Sheet, edges: list[Edge], gutter: int, runs: list[Edge]) -> dict[tuple[str, str], Lane]:
    level = lane_levels(sheet, edges, gutter, 1)[0]
    return {(edge.source, edge.target): Lane(departure_x(sheet, edge.source, edge.target), arrival_x(sheet, edge.source, edge.target), level) for edge in runs}
    # The converging runs share one level below a label band, so each label sits beside its own line where it leaves its box, above the turn, as a sketch writes it.


def crowded_gutters(sheet: Sheet, edges: list[Edge]) -> dict[int, list[Edge]]:
    routes = {edge.link: route_points(sheet, edge.source, edge.target) for edge in edges}
    runs: dict[int, list[Edge]] = {}
    for edge in [edge for edge in edges if is_gutter_run(sheet, routes[edge.link])]:
        runs.setdefault(sheet.channels_y.index(routes[edge.link][1][1]), []).append(edge)
    return {gutter: members for gutter, members in runs.items() if any(shares_a_line(sheet, edge, edges, routes) for edge in members)}
    # A run is an edge that drops into a gutter, crosses it, and leaves it; a gutter is crowded when one of its runs lies along a line of another edge that is not a leg of the same bus.


def is_gutter_run(sheet: Sheet, points: list[tuple[float, float]]) -> bool:
    if len(points) != 4:
        return False
    (first_x, _), (bend_x, level), (other_bend_x, other_level), (last_x, _) = points
    return first_x == bend_x and other_bend_x == last_x and level == other_level and level in sheet.channels_y


def shares_a_line(sheet: Sheet, edge: Edge, edges: list[Edge], routes: dict[str, list[tuple[float, float]]]) -> bool:
    others = [other for other in edges if other.link != edge.link and not is_same_bus(sheet, edge, other)]
    return any(runs_along(own, theirs) for other in others for own in segments(routes[edge.link]) for theirs in segments(routes[other.link]))


def is_same_bus(sheet: Sheet, edge: Edge, other: Edge) -> bool:
    return edge.source == other.source and {(edge.source, edge.target), (other.source, other.target)} <= sheet.bus_legs


def runs_along(first: tuple[tuple[float, float], tuple[float, float]], second: tuple[tuple[float, float], tuple[float, float]]) -> bool:
    (first_x, first_y), (first_end_x, first_end_y) = first
    (second_x, second_y), (second_end_x, second_end_y) = second
    if first_y == first_end_y == second_y == second_end_y:
        return min(max(first_x, first_end_x), max(second_x, second_end_x)) > max(min(first_x, first_end_x), min(second_x, second_end_x))
    if first_x == first_end_x == second_x == second_end_x:
        return min(max(first_y, first_end_y), max(second_y, second_end_y)) > max(min(first_y, first_end_y), min(second_y, second_end_y))
    return False


def lane_room(sheet: Sheet, edges: list[Edge], gutter: int, count: int) -> float:
    return label_band(sheet, edges, gutter) + (count - 1) * LANE_GAP + ROW_GAP / 2


def label_band(sheet: Sheet, edges: list[Edge], gutter: int) -> float:
    starting = [edge.label.height for edge in edges if edge.label is not None and sheet.cells[edge.source].row == gutter - 1 < sheet.cells[edge.target].row]
    return max([ROW_GAP / 2] + [height + 2 * LABEL_CLEARANCE for height in starting])
    # The labels of the lines starting down into the gutter sit above its levels, beside their own lines, as a sketch writes them.


def lane_levels(sheet: Sheet, edges: list[Edge], gutter: int, count: int) -> list[float]:
    top = sheet.channels_y[gutter] + (label_band(sheet, edges, gutter) - ROW_GAP / 2) / 2 - (count - 1) * LANE_GAP / 2
    return [top + index * LANE_GAP for index in range(count)]


def lane_choices(sheet: Sheet, edges: list[Edge], gutter: int, runs: list[Edge]) -> list[dict[tuple[str, str], Lane]]:
    levels = lane_levels(sheet, edges, gutter, len(runs))
    widest_first = sorted(runs, key=lambda edge: -abs(sheet.cells[edge.target].column - sheet.cells[edge.source].column))
    return [choice for order in permutations(widest_first) for choice in port_choices(sheet, dict(zip(order, levels)))]
    # The choices come in order of preference, so among equally tidy ones the run reaching furthest takes the highest level, as a nested staircase is drawn.


def port_choices(sheet: Sheet, levels: dict[Edge, float]) -> list[dict[tuple[str, str], Lane]]:
    groups: dict[tuple[int, int], list[Stub]] = {}
    for stub in [Stub(edge, departs) for edge in levels for departs in (True, False)]:
        groups.setdefault(stub_side(sheet, stub), []).append(stub)
    inner_first = [sorted(stubs, key=lambda stub: -levels[stub.edge]) for stubs in groups.values()]
    return [lanes_from(sheet, levels, arrangement) for arrangement in product(*[list(permutations(stubs)) for stubs in inner_first])]
    # The stubs on one half of a column, whether leaving the box above the gutter or entering the box below it, are spread across that half; the higher run is preferred on the outside.


def stub_side(sheet: Sheet, stub: Stub) -> tuple[int, int]:
    node, other = stub_ends(stub)
    column = sheet.cells[node].column
    return column, -1 if sheet.cells[other].column < column else 1


def stub_ends(stub: Stub) -> tuple[str, str]:
    return (stub.edge.source, stub.edge.target) if stub.departs else (stub.edge.target, stub.edge.source)


def lanes_from(sheet: Sheet, levels: dict[Edge, float], arrangement: tuple[tuple[Stub, ...], ...]) -> dict[tuple[str, str], Lane]:
    xs = {stub: stub_x(sheet, stub, (index + 1) / (len(stubs) + 1)) for stubs in arrangement for index, stub in enumerate(stubs)}
    return {(edge.source, edge.target): Lane(xs[Stub(edge, True)], xs[Stub(edge, False)], level) for edge, level in levels.items()}


def stub_x(sheet: Sheet, stub: Stub, outwardness: float) -> float:
    node, _ = stub_ends(stub)
    box = sheet.boxes[node]
    return box.center_x + stub_side(sheet, stub)[1] * box.width * 2 * ATTACHMENT_FRACTION * outwardness
    # A lone stub lands where any edge attaches, a quarter of the width from the centre; several share that half evenly.


def fewest_crossings(sheet: Sheet, edges: list[Edge], choices: list[dict[tuple[str, str], Lane]]) -> dict[tuple[str, str], Lane]:
    return min(choices, key=lambda choice: crossings([route_points(sheet._replace(lanes={**sheet.lanes, **choice}), edge.source, edge.target) for edge in edges]))


def crossings(routes: list[list[tuple[float, float]]]) -> int:
    lines = [(index, segment) for index, points in enumerate(routes) for segment in segments(points)]
    return sum(crossing_weight(first, second) for (owner, first), (other_owner, second) in combinations(lines, 2) if owner != other_owner)


def crossing_weight(first: tuple[tuple[float, float], tuple[float, float]], second: tuple[tuple[float, float], tuple[float, float]]) -> int:
    if runs_along(first, second):
        return SHARED_LINE_WEIGHT
    return int(crosses(first, second) or crosses(second, first))
    # Two lines on one stretch read as one edge, which is far worse than a crossing, so it is weighed as many crossings.


def crosses(across: tuple[tuple[float, float], tuple[float, float]], down: tuple[tuple[float, float], tuple[float, float]]) -> bool:
    (left, y), (right, other_y) = across
    (x, top), (other_x, bottom) = down
    return y == other_y and x == other_x and min(left, right) < x < max(left, right) and min(top, bottom) < y < max(top, bottom)


def label_boxes(sheet: Sheet, edges: list[Edge], routes: dict[str, list[tuple[float, float]]], titles_x: dict[str, float]) -> dict[str, Box]:
    return {link: box for link, (box, _) in placed_labels(sheet, edges, routes, titles_x).items()}


def placed_labels(sheet: Sheet, edges: list[Edge], routes: dict[str, list[tuple[float, float]]], titles_x: dict[str, float]) -> dict[str, tuple[Box, bool]]:
    obstacles = list(sheet.boxes.values()) + [title_strip(sheet, name, titles_x[name]) for name in sheet.containers]
    obstacles += [border for rect in sheet.containers.values() for border in border_boxes(rect)]
    placed: dict[str, tuple[Box, bool]] = {}
    for edge in [edge for edge in edges if edge.label is not None]:
        other_lines = [line_box(segment) for link, points in routes.items() if link != edge.link for segment in segments(points)]
        blocking = obstacles + other_lines + [box for box, _ in placed.values()]
        box = label_box(sheet, edge, edges, routes, blocking)
        placed[edge.link] = (box, not any(overlaps(with_margin(box), other) for other in blocking))
    return placed
    # Each label is placed in turn and recorded with whether it found a clear spot, so the layout can tell when converging labels have nowhere to go.


def label_box(sheet: Sheet, edge: Edge, edges: list[Edge], routes: dict[str, list[tuple[float, float]]], blocking: list[Box]) -> Box:
    if (edge.source, edge.target) in sheet.fans:
        _, border = sheet.fans[(edge.source, edge.target)]
        level = routes[edge.link][-1][1]
        return free_label_box([(sheet.fans[(edge.source, edge.target)][0], level), (border, level)], edge.label, blocking)
    if (edge.source, edge.target) in sheet.departures:
        stretch = staggered_label_stretch(sheet, edge, edges, routes)
        return outward_label_box(edge, stretch, stretch[0][0] - facing_side(sheet, edge.source, edge.target), blocking)
    if is_hub_edge(sheet, edge) and (edge.source, edge.target) in sheet.lanes:
        leg = routes[edge.link][-2:] if edge.source in sheet.spanned else routes[edge.link][:2]
        return outward_label_box(edge, leg, leg[0][0], blocking)
    if (edge.source, edge.target) in sheet.entries:
        stretch = entry_label_stretch(sheet, edge, routes[edge.link])
        return outward_label_box(edge, stretch, stretch[0][0], blocking)
    if is_tucked_elbow(sheet, edge.source, edge.target):
        drop = routes[edge.link][:2] if sheet.cells[edge.target].row > sheet.cells[edge.source].row else routes[edge.link][1:]
        return outward_label_box(edge, drop, drop[0][0], blocking)
    if is_opposed_vertical(sheet, edge, routes[edge.link]):
        return outward_label_box(edge, stretch_beside_lower_box(sheet, edge, routes[edge.link]), shared_middle(sheet.boxes[edge.source], sheet.boxes[edge.target]), blocking)
    if is_parallel_leg(sheet, edge, edges, routes):
        return outward_label_box(edge, leg_above_lanes(sheet, routes[edge.link]), legs_middle(sheet, edge, edges, routes), blocking)
    if is_fan_in_leg(sheet, edge, edges, routes):
        return outward_label_box(edge, leg_above_lanes(sheet, routes[edge.link]), routes[edge.link][0][0], blocking)
    return free_label_box(label_route(sheet, edge, routes[edge.link]), edge.label, blocking)


def is_parallel_leg(sheet: Sheet, edge: Edge, edges: list[Edge], routes: dict[str, list[tuple[float, float]]]) -> bool:
    return is_leg(sheet, edge, routes[edge.link]) and len(legs_of(sheet, edge, edges, routes)) > 1


def is_fan_in_leg(sheet: Sheet, edge: Edge, edges: list[Edge], routes: dict[str, list[tuple[float, float]]]) -> bool:
    converging = [other for other in fan_in_edges(sheet.cells, edges) if other.target == edge.target]
    return edge in converging and is_leg(sheet, edge, routes[edge.link]) and any((other.source, other.target) in sheet.lanes for other in converging)
    # Once converging lines share a level, each label goes on the right of its own line, level with the others.


def is_leg(sheet: Sheet, edge: Edge, points: list[tuple[float, float]]) -> bool:
    return is_straight_drop(points) or (edge.source, edge.target) in sheet.lanes
    # A staircase is a leg only in a crowded gutter, where its crossing stretch is packed between other levels; elsewhere its label keeps its longest clear segment.


def legs_of(sheet: Sheet, edge: Edge, edges: list[Edge], routes: dict[str, list[tuple[float, float]]]) -> list[Edge]:
    return [other for other in edges if other.source == edge.source and is_leg(sheet, other, routes[other.link])]


def legs_middle(sheet: Sheet, edge: Edge, edges: list[Edge], routes: dict[str, list[tuple[float, float]]]) -> float:
    departures = [routes[leg.link][0][0] for leg in legs_of(sheet, edge, edges, routes)]
    return (min(departures) + max(departures)) / 2
    # A leg left of the middle of its box's legs has its label on the left, one right of it on the right, so a leg dropping from the centre beside an offset one still has a side.


def leg_above_lanes(sheet: Sheet, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    (x, first_y), (_, second_y) = points[:2]
    levels = [lane.level for lane in sheet.lanes.values() if min(first_y, second_y) < lane.level < max(first_y, second_y)]
    return [(x, first_y), (x, min(levels, key=lambda level: abs(level - first_y), default=second_y))]
    # A leg's label stays above the levels of a crowded gutter, where the other runs cross, so the labels of legs side by side are level with each other.


def is_opposed_vertical(sheet: Sheet, edge: Edge, points: list[tuple[float, float]]) -> bool:
    return (edge.source, edge.target) in sheet.opposed and len(points) == 2 and points[0][0] == points[1][0]
    # The downward and upward lines of a vertical pair are too close for a label between them, so each label goes outside its own line.


def stretch_beside_lower_box(sheet: Sheet, edge: Edge, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    (x, first_y), (_, second_y) = points
    borders = [y for rect in sheet.containers.values() if rect.x < x < rect.right for y in (rect.y, rect.bottom) if min(first_y, second_y) < y < max(first_y, second_y)]
    if not borders or abs(sheet.cells[edge.target].row - sheet.cells[edge.source].row) == 1:
        return points
    if second_y > first_y:
        return [(x, max(borders)), (x, second_y)]
    return [(x, first_y), (x, max(borders) + ARROW_GAP)]
    # A pair that passes a row and crosses a container's border keeps its labels below the last border it crosses, beside the box it reaches there, rather than halfway down among the passed row's boxes.


def is_straight_drop(points: list[tuple[float, float]]) -> bool:
    return len(points) == 2 and points[0][0] == points[1][0] and points[1][1] > points[0][1]


def outward_label_box(edge: Edge, points: list[tuple[float, float]], middle_x: float, obstacles: list[Box]) -> Box:
    (x, first_y), (_, second_y) = points
    top, bottom = (first_y, second_y) if second_y > first_y else (second_y - ARROW_GAP, first_y - ARROW_GAP)
    leftward = x < middle_x
    left = x - LABEL_CLEARANCE - edge.label.width if leftward else x + LABEL_CLEARANCE
    candidates = [Box(left, top + (bottom - top) * position - edge.label.height / 2, edge.label.width, edge.label.height) for position in LABEL_POSITIONS]
    return next((box for box in candidates if not any(overlaps(with_margin(box), other) for other in obstacles)), free_label_box(points, edge.label, obstacles))
    # Two straight vertical lines side by side, the legs from one box or an opposed pair, have no room for a label between them, so each label sits outside the pair, beside its own line, as a sketch writes it.
    # An upward line keeps its arrowhead gap at the top; shifting its span by that gap levels its label with the downward line's.


def label_route(sheet: Sheet, edge: Edge, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if (edge.source, edge.target) in sheet.passes or lands_beside_a_pass(sheet, edge, points):
        return past_last_border(sheet, points[-2:])
    return points[-2:] if returns_by_the_right(sheet, edge.source, edge.target) or is_rise(sheet, edge.source, edge.target) else points
    # A returning edge's label sits on its last leg, beside the box it feeds back into, rather than out on the far vertical.


def lands_beside_a_pass(sheet: Sheet, edge: Edge, points: list[tuple[float, float]]) -> bool:
    return len(points) == 2 and points[0][0] == points[1][0] and any(target == edge.target for _, target in sheet.passes)
    # A straight line into the box a passing line lands on keeps its label past the same border, so the labels of the two lines sit level.


def past_last_border(sheet: Sheet, stretch: list[tuple[float, float]]) -> list[tuple[float, float]]:
    (x, first_y), (_, last_y) = stretch
    borders = [y for rect in sheet.containers.values() if rect.x < x < rect.right for y in (rect.y, rect.bottom) if min(first_y, last_y) < y < max(first_y, last_y)]
    if not borders:
        return stretch
    return [(x, max(borders) if last_y > first_y else min(borders)), (x, last_y)]
    # A line passing beside a column keeps its label past the last border it crosses, beside the box it lands on, not halfway down beside a box it only passes.


def line_box(segment: tuple[tuple[float, float], tuple[float, float]]) -> Box:
    (first_x, first_y), (second_x, second_y) = segment
    return Box(min(first_x, second_x), min(first_y, second_y), abs(second_x - first_x), abs(second_y - first_y))
    # Another edge's line is an obstacle too: a label centred on its own line must not sit on a line it does not belong to.


def title_strip(sheet: Sheet, name: str, title_x: float) -> Box:
    rect = sheet.containers[name]
    return Box(title_x - TITLE_INSET, rect.y, min(rect.width, sheet.title_widths[name] + 2 * TITLE_INSET), sheet.strips[name])


def border_boxes(rect: Box) -> list[Box]:
    across, down = Box(rect.x, -1.0, rect.width, 2.0), Box(-1.0, rect.y, 2.0, rect.height)
    return [across._replace(y=rect.y - 1), across._replace(y=rect.bottom - 1), down._replace(x=rect.x - 1), down._replace(x=rect.right - 1)]
    # A label drawn over a container's outline knocks a white gap into it, so each of the four border lines is a thin obstacle.


def title_x_positions(sheet: Sheet, routes: dict[str, list[tuple[float, float]]]) -> dict[str, float]:
    positions: dict[str, float] = {}
    for name, rect in sheet.containers.items():
        crossings = sorted(x for x in strip_crossings(rect, sheet.strips[name], routes) if x > rect.x + TITLE_INSET)
        width, x = sheet.title_widths[name], rect.x + TITLE_INSET
        for crossing in crossings:
            if x - LABEL_CLEARANCE < crossing < x + width + LABEL_CLEARANCE:
                x = crossing + LABEL_CLEARANCE
        positions[name] = x if x + width <= rect.right - TITLE_INSET else rect.x + TITLE_INSET
        # An edge dropping into the container's top row must cross the title strip, so the title slides right past every such crossing; if nothing fits, it stays at the left.
    return positions


def strip_crossings(rect: Box, strip: float, routes: dict[str, list[tuple[float, float]]]) -> list[float]:
    strip_bottom = rect.y + strip
    verticals = [(first[0], first[1], second[1]) for points in routes.values() for first, second in segments(points) if first[0] == second[0]]
    return [x for x, start_y, end_y in verticals if rect.x < x < rect.right and min(start_y, end_y) < strip_bottom and max(start_y, end_y) > rect.y]


def free_label_box(points: list[tuple[float, float]], size: Box, obstacles: list[Box]) -> Box:
    candidates = [placed_along(segment, size, position) for segment in sorted(segments(points), key=segment_length, reverse=True) for position in LABEL_POSITIONS]
    return next((box for box in candidates if not any(overlaps(with_margin(box), other) for other in obstacles)), candidates[0])
    # The middle of the longest segment is tried first; when that is taken the label slides along its own line, so a straight edge through a title strip or a crossing still finds a clear stretch.


def placed_along(segment: tuple[tuple[float, float], tuple[float, float]], size: Box, position: float) -> Box:
    (first_x, first_y), (second_x, second_y) = segment
    x, y = first_x + (second_x - first_x) * position, first_y + (second_y - first_y) * position
    return Box(x - size.width / 2, y - size.height / 2, size.width, size.height)


def with_margin(box: Box) -> Box:
    return Box(box.x - LABEL_MARGIN, box.y - LABEL_MARGIN, box.width + 2 * LABEL_MARGIN, box.height + 2 * LABEL_MARGIN)


def segments(points: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return list(zip(points, points[1:]))


def segment_length(segment: tuple[tuple[float, float], tuple[float, float]]) -> float:
    return abs(segment[1][0] - segment[0][0]) + abs(segment[1][1] - segment[0][1])


def overlaps(box: Box, other: Box) -> bool:
    return box.overlaps_horizontally(other) and box.overlaps_vertically(other)


def move_nodes(svg: str, sheet: Sheet) -> str:
    def moved(match: re.Match[str]) -> str:
        box, anchor = sheet.boxes[match["name"]], sheet.anchors[match["name"]]
        return f'{match["head"]}{box.center_x - anchor[0]:g}, {box.center_y - anchor[1]:g}{match["tail"]}'
        # The anchor is where the shape's own coordinates put its centre, so a corner-drawn cylinder lands in its cell like a centre-drawn rect.

    return NODE_TRANSFORM.sub(moved, svg)


def draw_containers(svg: str, sheet: Sheet, titles_x: dict[str, float]) -> str:
    def drawn(match: re.Match[str]) -> str:
        name = match["id"].split("-")[-1]
        rect, title_x = sheet.containers[name], titles_x[name]
        return cluster_markup(match, rect, title_x, rect.y + TITLE_GAP, rect.right - TITLE_INSET - title_x)

    return CLUSTER.sub(drawn, svg)


def draw_edges(svg: str, routes: dict[str, list[tuple[float, float]]], joined: frozenset[str]) -> str:
    def drawn(match: re.Match[str]) -> str:
        points = routes.get(match["link"])
        return match.group(0) if points is None else f'{match["head"]}{polyline(points)}{match["tail"]}'

    return without_arrowheads(EDGE_PATH.sub(drawn, svg), joined)


def without_arrowheads(svg: str, links: frozenset[str]) -> str:
    return EDGE_MARKER.sub(lambda match: match["path"] if match["link"] in links else match.group(0), svg)
    # A fan-in leg that ends on the trunk, or on the straight line it joins, has no arrowhead of its own: the line it joins carries the one into the target.


def polyline(points: list[tuple[float, float]]) -> str:
    return "M" + "L".join(f"{x:g},{y:g}" for x, y in points)


def draw_labels(svg: str, labels: dict[str, Box]) -> str:
    def drawn(match: re.Match[str]) -> str:
        box = labels.get(match["link"])
        return match.group(0) if box is None else f'{match["head"]}{box.center_x:g}, {box.center_y:g}{match["tail"]}'

    return EDGE_LABEL.sub(drawn, svg)


def reframe(svg: str, sheet: Sheet, routes: dict[str, list[tuple[float, float]]], labels: dict[str, Box]) -> str:
    drawn = list(sheet.containers.values()) + list(sheet.boxes.values()) + list(labels.values())
    drawn += [Box(x, y, 0, 0) for points in routes.values() for x, y in points]
    content = bounds(drawn)
    return FRAME.sub(lambda match: framed(content), svg, count=1)


def framed(content: Box) -> str:
    width, height = content.right + MARGIN, content.bottom + MARGIN
    return f'style="max-width: {width:g}px; background-color: white;" viewBox="0 0 {width:g} {height:g}"'

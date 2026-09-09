"""Post-processing of a mermaid SVG so it meets the readability rules that Mermaid and ELK cannot be configured for.

Every subgraph is one layer. In a top-down diagram the layers become full-width bands with the title at the left; in a left-to-right diagram they become full-height columns with the title at the top. Node corners are rounded and the container corners more so.
"""

import re
from typing import NamedTuple

CLUSTER = re.compile(
    r'(?P<head><g class="cluster" id="[^"]*" data-look="classic"><rect style="[^"]*" x=")(?P<x>[\d.\-]+)" y="(?P<y>[\d.\-]+)" width="(?P<w>[\d.\-]+)" height="(?P<h>[\d.\-]+)'
    r'(?P<mid>"/><g class="cluster-label" transform="translate\()(?P<lx>[\d.\-]+), (?P<ly>[\d.\-]+)(?P<tail>\)")'
)
TITLE_INSET = 16
NODE_RADIUS = 8
CONTAINER_RADIUS = 12


class Box(NamedTuple):
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def overlaps_vertically(self, other: "Box") -> bool:
        return self.y < other.bottom and other.y < self.bottom

    def overlaps_horizontally(self, other: "Box") -> bool:
        return self.x < other.right and other.x < self.right


def polish(svg: str) -> str:
    return round_corners(band_layers(svg))


def band_layers(svg: str) -> str:
    boxes = [cluster_box(match) for match in CLUSTER.finditer(svg)]
    if len(boxes) < 2:
        return svg
    if not any(a.overlaps_vertically(b) for a, b in pairs(boxes)):
        return CLUSTER.sub(lambda match: as_row(match, min(box.x for box in boxes), max(box.right for box in boxes)), svg)
    if not any(a.overlaps_horizontally(b) for a, b in pairs(boxes)):
        return CLUSTER.sub(lambda match: as_column(match, min(box.y for box in boxes), max(box.bottom for box in boxes)), svg)
    return svg
    # Layers that overlap both ways are nested or scattered, which the authoring rules forbid; such a drawing is left as ELK made it.


def cluster_box(match: re.Match[str]) -> Box:
    return Box(float(match["x"]), float(match["y"]), float(match["w"]), float(match["h"]))


def pairs(boxes: list[Box]) -> list[tuple[Box, Box]]:
    return [(boxes[i], boxes[j]) for i in range(len(boxes)) for j in range(i + 1, len(boxes))]


def as_row(match: re.Match[str], left: float, right: float) -> str:
    box = cluster_box(match)
    return cluster_markup(match, Box(left, box.y, right - left, box.height), left + TITLE_INSET, float(match["ly"]))


def as_column(match: re.Match[str], top: float, bottom: float) -> str:
    box = cluster_box(match)
    title_y = top + (float(match["ly"]) - box.y)
    return cluster_markup(match, Box(box.x, top, box.width, bottom - top), box.x + TITLE_INSET, title_y)


def cluster_markup(match: re.Match[str], box: Box, title_x: float, title_y: float) -> str:
    return f'{match["head"]}{box.x:g}" y="{box.y:g}" width="{box.width:g}" height="{box.height:g}{match["mid"]}{title_x:g}, {title_y:g}{match["tail"]}'


def round_corners(svg: str) -> str:
    rounded_nodes = svg.replace('rx="5" ry="5"', f'rx="{NODE_RADIUS}" ry="{NODE_RADIUS}"')
    return rounded_nodes.replace('data-look="classic"><rect style="" x=', f'data-look="classic"><rect rx="{CONTAINER_RADIUS}" ry="{CONTAINER_RADIUS}" style="" x=')

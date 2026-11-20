"""Post-processing of a mermaid SVG so it meets the readability rules that Mermaid and ELK cannot be configured for.

Every subgraph is one layer. In a top-down diagram the layers become full-width bands and their titles move into a header column at the left; in a left-to-right diagram they become full-height columns with their titles in a strip along the top. Edges never enter the header gutter, so no title is ever crossed. Node corners are rounded and container corners more so. Every edge label is filled with the colour behind it, so it stays opaque over the lines yet blends into its container.
"""

import re
from typing import NamedTuple

CLUSTER = re.compile(
    r'(?P<head><g class="cluster" id="(?P<id>[^"]*)" data-look="classic"><rect style="[^"]*" x=")(?P<x>[\d.\-]+)" y="(?P<y>[\d.\-]+)" width="(?P<w>[\d.\-]+)" height="(?P<h>[\d.\-]+)'
    r'(?P<mid>"/><g class="cluster-label" transform="translate\()(?P<lx>[\d.\-]+), (?P<ly>[\d.\-]+)\)"><foreignObject width="(?P<lw>[\d.]+)" height="(?P<lh>[\d.]+)">'
    r'<div xmlns="http://www.w3.org/1999/xhtml" style="[^"]*">(?P<inner><span class="nodeLabel"><p>(?P<text>.*?)</p></span>)</div>'
)
EDGE_PATH = re.compile(r'<path d="(?P<d>[^"]+)"[^>]*flowchart-link')
EDGE_LABEL = re.compile(
    r'<g class="edgeLabel" transform="translate\((?P<x>[\d.\-]+), (?P<y>[\d.\-]+)\)"><g class="label"[^>]*transform="translate\((?P<dx>[\d.\-]+), (?P<dy>[\d.\-]+)\)"><foreignObject width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)"'
)
FRAME = re.compile(r'style="max-width: (?P<w>[\d.]+)px; background-color: white;" viewBox="(?P<vx>[\d.\-]+) (?P<vy>[\d.\-]+) (?P<vw>[\d.\-]+) (?P<vh>[\d.\-]+)"')
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
CLUSTER_RECT = re.compile(
    r'<g class="cluster" id="[^"]*"[^>]*><rect (?:rx="[\d.]+" ry="[\d.]+" )?style="(?P<style>[^"]*)" x="(?P<x>[\d.\-]+)" y="(?P<y>[\d.\-]+)" width="(?P<w>[\d.\-]+)" height="(?P<h>[\d.\-]+)"'
)
UNROUNDED_CLUSTER_RECT = re.compile(r'(?P<head><g class="cluster" id="[^"]*" data-look="classic"><rect )(?=style=")')
CLUSTER_CSS_FILL = re.compile(r"\.cluster rect\{fill:(?P<fill>[^;}]+)")
INLINE_FILL = re.compile(r"(?:^|;)\s*fill:\s*(?P<fill>[^;!]+)")
LABEL_BACKGROUND = re.compile(
    r'(?P<head><g class="edgeLabel" transform="translate\((?P<x>[\d.\-]+), (?P<y>[\d.\-]+)\)"><g class="label"[^>]*><foreignObject[^>]*>'
    r'<div xmlns="http://www.w3.org/1999/xhtml" class="labelBkg" style=")(?P<style>[^"]*)(?P<tail>"><span class="edgeLabel")(?P<text>><p)?'
)
DIAGRAM_BACKGROUND = "#ffffff"
# White: the frame gives every SVG a white background and the handbook shows each one on a white card in both colour schemes.
LABEL_FILL_SPREAD = 999
TITLE_INSET = 16
TITLE_WIDTH = 180
LINE_HEIGHT = 21
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

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    def overlaps_vertically(self, other: "Box") -> bool:
        return self.y < other.bottom and other.y < self.bottom

    def overlaps_horizontally(self, other: "Box") -> bool:
        return self.x < other.right and other.x < self.right


class Title(NamedTuple):
    text: str
    natural_width: float
    natural_height: float

    def wrapped(self, width: float) -> list[str]:
        char_width = self.natural_width / max(1, len(self.text))
        return wrap_words(self.text.split(), width / char_width)

    def wrapped_height(self, width: float) -> float:
        return len(self.wrapped(width)) * LINE_HEIGHT


def wrap_words(words: list[str], chars_per_line: float) -> list[str]:
    lines: list[str] = []
    for word in words:
        if lines and len(lines[-1]) + 1 + len(word) <= chars_per_line:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines or [""]


def band_layers(svg: str) -> str:
    clusters = list(CLUSTER.finditer(svg))
    boxes = [cluster_box(match) for match in clusters]
    if len(boxes) < 2:
        return svg
    content = content_box(svg, boxes)
    if not any(a.overlaps_vertically(b) for a, b in pairs(boxes)):
        gutter = TITLE_WIDTH + 2 * TITLE_INSET
        return frame(CLUSTER.sub(lambda match: as_row(match, content.x - gutter, content.right), svg), content.x - gutter, content.y)
    if not any(a.overlaps_horizontally(b) for a, b in pairs(boxes)):
        gutter = max(title_of(match).wrapped_height(cluster_box(match).width - 2 * TITLE_INSET) for match in clusters) + 2 * TITLE_INSET
        return frame(CLUSTER.sub(lambda match: as_column(match, content.y - gutter, content.bottom), svg), content.x, content.y - gutter)
    return svg
    # Layers that overlap both ways are nested or scattered, which the authoring rules forbid; such a drawing is left as ELK made it.


def cluster_box(match: re.Match[str]) -> Box:
    return Box(float(match["x"]), float(match["y"]), float(match["w"]), float(match["h"]))


def title_of(match: re.Match[str]) -> Title:
    return Title(match["text"], float(match["lw"]), float(match["lh"]))


def pairs(boxes: list[Box]) -> list[tuple[Box, Box]]:
    return [(boxes[i], boxes[j]) for i in range(len(boxes)) for j in range(i + 1, len(boxes))]


def content_box(svg: str, clusters: list[Box]) -> Box:
    xs = [box.x for box in clusters] + [box.right for box in clusters]
    ys = [box.y for box in clusters] + [box.bottom for box in clusters]
    for match in EDGE_PATH.finditer(svg):
        numbers = [float(n) for n in NUMBER.findall(match["d"])]
        xs += numbers[0::2]
        ys += numbers[1::2]
    for match in EDGE_LABEL.finditer(svg):
        left, top = float(match["x"]) + float(match["dx"]), float(match["y"]) + float(match["dy"])
        xs += [left, left + float(match["w"])]
        ys += [top, top + float(match["h"])]
    return Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def as_row(match: re.Match[str], left: float, right: float) -> str:
    box = cluster_box(match)
    title = title_of(match)
    top = box.y + title.natural_height + TITLE_INSET / 2
    # ELK reserved the top of the band for the title; with the title in the gutter that strip is given back.
    band = Box(left, top, right - left, box.bottom - top)
    title_y = band.y + (band.height - title.wrapped_height(TITLE_WIDTH)) / 2
    return cluster_markup(match, band, left + TITLE_INSET, title_y, TITLE_WIDTH)


def as_column(match: re.Match[str], top: float, bottom: float) -> str:
    box = cluster_box(match)
    column = Box(box.x, top, box.width, bottom - top)
    return cluster_markup(match, column, box.x + TITLE_INSET, top + TITLE_INSET, box.width - 2 * TITLE_INSET)


def cluster_markup(match: re.Match[str], box: Box, title_x: float, title_y: float, title_width: float) -> str:
    title = title_of(match)
    label = (
        f'<foreignObject width="{title_width:g}" height="{title.wrapped_height(title_width):g}" style="overflow: visible;">'
        f'<div xmlns="http://www.w3.org/1999/xhtml" style="display: block; width: {title_width:g}px; white-space: normal; overflow-wrap: anywhere; line-height: 1.5;">{match["inner"]}</div>'
    )
    return f'{match["head"]}{box.x:g}" y="{box.y:g}" width="{box.width:g}" height="{box.height:g}{match["mid"]}{title_x:g}, {title_y:g})">{label}'
    # The height is an estimate from average character width; overflow stays visible so a title that wraps one line further is never clipped.


def frame(svg: str, left: float, top: float) -> str:
    def widen(match: re.Match[str]) -> str:
        x, y = min(float(match["vx"]), left - 4), min(float(match["vy"]), top - 4)
        width, height = float(match["vx"]) + float(match["vw"]) - x, float(match["vy"]) + float(match["vh"]) - y
        return f'style="max-width: {width:g}px; background-color: white;" viewBox="{x:g} {y:g} {width:g} {height:g}"'

    return FRAME.sub(widen, svg, count=1)


def round_corners(svg: str) -> str:
    rounded_nodes = svg.replace('rx="5" ry="5"', f'rx="{NODE_RADIUS}" ry="{NODE_RADIUS}"')
    return UNROUNDED_CLUSTER_RECT.sub(rf'\g<head>rx="{CONTAINER_RADIUS}" ry="{CONTAINER_RADIUS}" ', rounded_nodes)
    # A container highlighted with `style` carries its stroke in the rect's style attribute, which is kept; only the corners are added.


def blend_label_backgrounds(svg: str) -> str:
    layers = container_layers(svg)

    def filled(match: re.Match[str]) -> str:
        background = label_background(fills_behind(layers, float(match["x"]), float(match["y"])))
        text = f'><p style="{background}"' if match["text"] else ""
        return f'{match["head"]}{match["style"]} {background}{match["tail"]} style="{background}"{text}'

    return LABEL_BACKGROUND.sub(filled, svg)
    # A label stays opaque, so no line shows through it, but shows the colour already behind it instead of Mermaid's white.


def container_layers(svg: str) -> list[tuple[Box, str]]:
    stylesheet_fill = CLUSTER_CSS_FILL.search(svg)
    layers = []
    for match in CLUSTER_RECT.finditer(svg):
        inline = INLINE_FILL.search(match["style"])
        fill = inline["fill"] if inline else stylesheet_fill["fill"] if stylesheet_fill else None
        if fill is not None:
            layers.append((Box(float(match["x"]), float(match["y"]), float(match["w"]), float(match["h"])), fill.strip()))
    return layers


def fills_behind(layers: list[tuple[Box, str]], x: float, y: float) -> list[str]:
    return [fill for box, fill in layers if box.x <= x <= box.right and box.y <= y <= box.bottom]
    # Containers are painted in document order, so the fills behind a point are listed bottom first.


def label_background(fills: list[str]) -> str:
    stacked = [f"inset 0 0 0 {LABEL_FILL_SPREAD}px {fill}" for fill in reversed(fills)]
    return f"background-color: {DIAGRAM_BACKGROUND};" + (f" box-shadow: {', '.join(stacked)};" if stacked else "")
    # The container fills are translucent and stack, so the label repaints the same stack over the page colour as solid inset shadows rather than one
    # precomputed colour: the browser then rounds both the same way, where a precomputed colour came out two levels lighter than the containers in Chrome.

"""Choosing how a rendered diagram is laid out: on the fixed grid when its source declares one, as bands otherwise, then rounded and with every edge label filled with the colour behind it."""

from diagrams.grid import grid_rows, lay_out_on_grid
from diagrams.polish import band_layers, blend_label_backgrounds, round_corners


def polish(svg: str, source: str = "") -> str:
    laid_out = lay_out_on_grid(svg, source) if grid_rows(source) else band_layers(svg)
    return round_corners(blend_label_backgrounds(laid_out))

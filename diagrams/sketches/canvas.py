"""A character canvas for ASCII diagram sketches: boxes, containers, and lines placed by coordinate, refusing any overlap."""

ROUNDED = ("╭", "╮", "╰", "╯")
CYLINDER = ("╭", "╮", "╰", "╯")


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.grid = [[" "] * width for _ in range(height)]

    def put(self, y: int, x: int, text: str) -> None:
        for offset, char in enumerate(text):
            here = self.grid[y][x + offset]
            assert here == " ", f"{text!r} collides at ({y},{x + offset}) with {here!r}"
            self.grid[y][x + offset] = char

    def box(self, y: int, center: int, lines: list[str], stored: bool = False) -> tuple[int, int, int]:
        width = max(len(line) for line in lines) + 4
        x = center - width // 2
        edge = "═" if stored else "─"
        rows = ["╭" + edge * (width - 2) + "╮"] + ["│ " + line.center(width - 4) + " │" for line in lines] + ["╰" + edge * (width - 2) + "╯"]
        for index, row in enumerate(rows):
            self.put(y + index, x, row)
        return x, x + width - 1, y + len(rows) - 1

    def container(self, top: int, left: int, bottom: int, right: int, title: str) -> None:
        self.frame(top, left, bottom, right)
        self.grid[top][left + 2 : left + 4 + len(title)] = list(" " + title + " ")

    def frame(self, top: int, left: int, bottom: int, right: int) -> None:
        self.put(top, left, "┌" + "─" * (right - left - 1) + "┐")
        for y in range(top + 1, bottom):
            self.put(y, left, "│")
            self.put(y, right, "│")
        self.put(bottom, left, "└" + "─" * (right - left - 1) + "┘")

    def decision(self, y: int, center: int, text: str) -> tuple[int, int, int]:
        width = len(text) + 6
        x = center - width // 2
        self.put(y, x + 1, "/" + "‾" * (width - 4) + "\\")
        self.put(y + 1, x, "<  " + text + "  >")
        self.put(y + 2, x + 1, "\\" + "_" * (width - 4) + "/")
        return x, x + width - 1, y + 2

    def vline(self, x: int, top: int, bottom: int, head: str = "▼", dashed: bool = False) -> None:
        for y in range(top, bottom + 1):
            self.grid[y][x] = self.crossing(y, x, "┆" if dashed else "│")
        if head == "▼":
            self.grid[bottom][x] = "▼"
        elif head == "▲":
            self.grid[top][x] = "▲"

    def hline(self, y: int, left: int, right: int, head: str = "▶", dashed: bool = False) -> None:
        for x in range(left, right + 1):
            self.grid[y][x] = self.crossing(y, x, "┄" if dashed else "─")
        if head == "▶":
            self.grid[y][right] = "▶"
        elif head == "◀":
            self.grid[y][left] = "◀"

    def corner(self, y: int, x: int, char: str) -> None:
        self.grid[y][x] = char

    def crossing(self, y: int, x: int, along: str) -> str:
        here = self.grid[y][x]
        assert here in " ─│┆┄", f"line {along!r} hits {here!r} at ({y},{x})"
        return along if here == " " or here == along else "┼"

    def render(self) -> str:
        return "\n".join("".join(row).rstrip() for row in self.grid)

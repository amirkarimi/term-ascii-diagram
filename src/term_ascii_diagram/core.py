import curses
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, overload


@dataclass
class Size:
    w: int
    h: int

    def set(self, other: "Size") -> None:
        self.w = other.w
        self.h = other.h

    def __add__(self, other: "Size") -> "Size":
        return Size(self.w + other.w, self.h + other.h)


@dataclass
class Point:
    x: int
    y: int

    def __add__(self, other: Size) -> "Point":
        return Point(self.x + other.w, self.y + other.h)

    @overload
    def __sub__(self, other: "Point") -> Size: ...
    @overload
    def __sub__(self, other: Size) -> "Point": ...

    def __sub__(self, other):
        if isinstance(other, Point):
            return Size(other.x - self.x, other.y - self.y)
        elif isinstance(other, Size):
            return Point(self.x - other.w, self.y - other.h)
        else:
            ValueError(f"Type {type(other).__name__} is not supported.")

    def set(self, other: "Point") -> None:
        self.x = other.x
        self.y = other.y

    def is_within(self, top_left: "Point", bottom_right: "Point") -> bool:
        return (
            top_left.x <= self.x <= bottom_right.x
            and top_left.y <= self.y <= bottom_right.y
        )


class Ascii(str, Enum):
    H_LINE = "─"
    V_LINE = "│"
    TL_CORNER = "┌"
    TR_CORNER = "┐"
    BL_CORNER = "└"
    BR_CORNER = "┘"
    ARROW_RIGHT = "⏵"
    ARROW_LEFT = "⏴"
    ARROW_UP = "⏶"
    ARROW_DOWN = "⏷"


class CursorMode(Enum):
    HAND = 0
    MOVE = 1


class Canvas:
    stdscr: curses.window

    def __init__(self, stdscr):
        self.stdscr = stdscr

    def getmaxxy(self) -> Tuple[int, int]:
        max_y, max_x = self.stdscr.getmaxyx()
        # Switch to be the same as other structures
        return max_x, max_y

    def set_color(self, color_profile: int) -> None:
        self.stdscr.attrset(curses.color_pair(color_profile))

    def reset_color(self) -> None:
        self.stdscr.attrset(curses.A_NORMAL)

    def read_keyboard_ch(self) -> int:
        return self.stdscr.getch()

    def put_ch(
        self,
        point: Point,
        ch: str,
        color_pair: Optional[int] = None,
    ) -> None:
        """Puts the given character in the given coordinates."""
        try:
            if color_pair is not None:
                self.stdscr.attrset(color_pair)
            self.stdscr.addch(point.y, point.x, ch)
            if color_pair is not None:
                self.stdscr.attrset(curses.A_NORMAL)
        except curses.error:
            # Do not put character when it's out side of screensize
            pass

    def put_str(self, point: Point, text: str) -> None:
        max_x, max_y = self.getmaxxy()
        if 0 <= point.x < max_x and 0 <= point.y < max_y:
            self.stdscr.addstr(point.y, point.x, text)

    def get_ch(self, point: Point) -> str:
        max_x, max_y = self.getmaxxy()
        if 0 <= point.x < max_x and 0 <= point.y < max_y:
            ch = self.stdscr.inch(point.y, point.x)
            # To handle unicode. A better alternative is to have a memory
            # buffer for characters and attributes.
            if ch & 0b11100000_00000000 == 0:
                return chr(ch & curses.A_CHARTEXT)
            else:
                return chr(ch)
        return ""

    def fill(self, start: Point, end: Point, ch: str) -> None:
        """Fills the given box with the given character."""
        sx, sy = start.x, start.y
        ex, ey = end.x, end.y

        # Support reverse direction
        if sx > ex:
            sx, ex = ex, sx
        if sy > ey:
            sy, ey = ey, sy

        for y in range(sy, ey + 1):
            for x in range(sx, ex + 1):
                self.put_ch(Point(x, y), ch)

    def refresh(self) -> None:
        """Refreshes the canvas/screen.

        Should be called after each frame.
        """
        self.stdscr.refresh()

    def clear(self) -> None:
        """Clears the canvas."""
        self.stdscr.clear()

    def resize(self, root: curses.window) -> None:
        max_y, max_x = root.getmaxyx()
        self.stdscr.resize(max_y - 1, max_x)

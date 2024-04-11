from copy import copy
import curses
import json
import math
import os
from curses.textpad import Textbox
from dataclasses import asdict
from enum import IntEnum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, cast

from term_ascii_diagram.core import Ascii, Canvas, CursorMode, Point, Size
from term_ascii_diagram.status_bar import StatusBar


class DiagramObject:
    position: Point
    size: Size

    def __init__(
        self,
        position: Optional[Point] = None,
        size: Optional[Size] = None,
    ):
        self.position = position or Point(0, 0)
        self.size = size or Size(6, 3)

    @property
    def normalized_position(self):
        x = self.position.x
        y = self.position.y
        if self.size.w < 0:
            x += self.size.w
        if self.size.h < 0:
            y += self.size.h
        return Point(x, y)

    @property
    def normalized_size(self):
        return Size(abs(self.size.w), abs(self.size.h))

    @property
    def top_left(self):
        return self.position

    @property
    def normalized_top_left(self):
        return self.normalized_position

    @property
    def top_right(self):
        return Point(self.position.x + self.size.w, self.position.y)

    @property
    def normalized_top_right(self):
        return Point(
            self.normalized_position.x + self.normalized_size.w,
            self.normalized_position.y,
        )

    @property
    def bottom_left(self):
        return Point(self.position.x, self.position.y + self.size.h)

    @property
    def normalized_bottom_left(self):
        return Point(
            self.normalized_position.x,
            self.normalized_position.y + self.normalized_size.h,
        )

    @property
    def bottom_right(self):
        return self.position + self.size

    @property
    def normalized_bottom_right(self):
        return self.normalized_position + self.normalized_size

    def draw(self, canvas: Canvas):
        """Draw the object on the canvas."""
        raise NotImplementedError("DiagramObject should not be used directly")

    def serialize(self) -> Dict[str, Any]:
        return {
            "type": type(self).__name__,
            "position": asdict(self.position),
            "size": asdict(self.size),
        }

    def deserialize(self, data: Dict[str, Any]) -> None:
        self.position.x = data["position"]["x"]
        self.position.y = data["position"]["y"]
        self.size.w = data["size"]["w"]
        self.size.h = data["size"]["h"]


class Box(DiagramObject):
    text: str
    show_border: bool

    def __init__(
        self,
        position: Optional[Point] = None,
        size: Optional[Size] = None,
        text: str = "",
        show_border: bool = True,
    ):
        super().__init__(position, size)
        self.text = text
        self.show_border = show_border

    def toggle(self) -> None:
        self.show_border = not self.show_border

    def draw(self, canvas: Canvas):
        if self.show_border:
            canvas.fill(self.top_left, self.top_right, Ascii.H_LINE)
            canvas.fill(self.bottom_left, self.bottom_right, Ascii.H_LINE)
            canvas.fill(self.top_right, self.bottom_right, Ascii.V_LINE)
            canvas.fill(self.top_left, self.bottom_left, Ascii.V_LINE)
            for point, char in [
                (self.normalized_top_left, Ascii.TL_CORNER),
                (self.normalized_top_right, Ascii.TR_CORNER),
                (self.normalized_bottom_left, Ascii.BL_CORNER),
                (self.normalized_bottom_right, Ascii.BR_CORNER),
            ]:
                canvas.put_ch(point, char)
        # Fill the box
        canvas.fill(
            self.top_left + Size(1, 1),
            self.bottom_right - Size(1, 1),
            " ",
        )
        text = self.text
        if not self.show_border and text.strip() == "":
            text = "[Text]"
        for i, line in enumerate(text.split("\n")[: self.size.h - 1]):
            canvas.put_str(
                self.top_left + Size(1, i + 1),
                line[: self.size.w - 1],
            )

    def serialize(self) -> Dict[str, Any]:
        data = super().serialize()
        data.update({"text": self.text, "show_border": self.show_border})
        return data

    def deserialize(self, data: Dict[str, Any]) -> None:
        super().deserialize(data)
        self.text = data["text"]
        self.show_border = data["show_border"]

    def edit(self, canvas: Canvas):
        buf = []
        for y in range(1, self.size.h):
            for x in range(1, self.size.w):
                ch = canvas.get_ch(
                    Point(
                        self.position.x + x,
                        self.position.y + y,
                    )
                )
                buf.append(ch)

        curses.curs_set(1)
        edit_win = curses.newwin(
            self.size.h - 1,
            self.size.w - 1,
            self.position.y + 1,
            self.position.x + 1,
        )
        box = Textbox(edit_win, insert_mode=True)
        # Restore the existing text
        for ch in buf:
            box.do_command(ch)
        edit_win.move(0, 0)
        box.stripspaces = False

        def validator(key: int) -> int:
            if key == curses.ascii.ESC:
                return curses.ascii.BEL  # ^g
            elif key == curses.KEY_DC:  # DEL
                return curses.ascii.EOT  # ^d
            else:
                return key

        # Let the user edit until Ctrl-G is struck.
        self.text = box.edit(validator)
        curses.curs_set(0)


class Line(DiagramObject):
    class Orientation(IntEnum):
        HORIZONTAL = 1
        VERTICAL = 2

    degree_to_ch = {
        0: Ascii.ARROW_DOWN,
        180: Ascii.ARROW_UP,
        90: Ascii.ARROW_RIGHT,
        -90: Ascii.ARROW_LEFT,
    }

    orientation: Orientation
    is_arrow: bool

    def __init__(
        self,
        position: Optional[Point] = None,
        is_arrow: bool = False,
        size: Optional[Size] = None,
        orientation: Optional[Orientation] = Orientation.HORIZONTAL,
    ):
        super().__init__(position, size)
        self.orientation = orientation or Line.Orientation.HORIZONTAL
        self.is_arrow = is_arrow

    def toggle(self):
        """Toggle the line starting orientation."""
        self.orientation = (
            Line.Orientation.HORIZONTAL
            if self.orientation == Line.Orientation.VERTICAL
            else Line.Orientation.VERTICAL
        )

    def _get_corner_ch(self, start: Point, end: Point) -> Ascii:
        x_forward = start.x <= end.x
        y_downwards = start.y <= end.y

        if self.orientation == Line.Orientation.HORIZONTAL:
            corners = {
                (True, True): Ascii.TR_CORNER,
                (True, False): Ascii.BR_CORNER,
                (False, True): Ascii.TL_CORNER,
                (False, False): Ascii.BL_CORNER,
            }
        else:
            corners = {
                (True, True): Ascii.BL_CORNER,
                (True, False): Ascii.TL_CORNER,
                (False, True): Ascii.BR_CORNER,
                (False, False): Ascii.TR_CORNER,
            }

        return corners[(x_forward, y_downwards)]

    def _draw_line(
        self,
        canvas: Canvas,
        start: Point,
        end: Point,
    ) -> None:
        if start.x != end.x and start.y != end.y:
            raise ValueError("Diagonal lines are not supported.")
        if start == end:
            return
        direction = Ascii.V_LINE if start.x == end.x else Ascii.H_LINE
        canvas.fill(start, end, direction)
        if self.is_arrow:
            # Draw the arrow end
            delta = start - end
            degree = math.atan2(delta.w, delta.h) / math.pi * 180
            arrow_end_ch = Line.degree_to_ch[int(degree)]
            canvas.put_ch(end, arrow_end_ch)

    def _draw_horizontal(self, canvas: Canvas) -> None:
        if self.top_left.y == self.bottom_right.y:
            self._draw_line(canvas, self.top_left, self.top_right)
        else:
            canvas.fill(self.top_left, self.top_right, Ascii.H_LINE)
            self._draw_line(
                canvas,
                self.top_right,
                self.bottom_right,
            )
            if self.top_left.x != self.bottom_right.x:
                canvas.put_ch(
                    self.top_right,
                    self._get_corner_ch(self.top_left, self.bottom_right),
                )

    def _draw_vertical(self, canvas: Canvas) -> None:
        if self.top_left.x == self.bottom_right.x:
            self._draw_line(canvas, self.top_left, self.bottom_left)
        else:
            canvas.fill(self.top_left, self.bottom_left, Ascii.V_LINE)
            self._draw_line(
                canvas,
                self.bottom_left,
                self.bottom_right,
            )
            if self.top_left.y != self.bottom_right.y:
                canvas.put_ch(
                    self.bottom_left,
                    self._get_corner_ch(self.top_left, self.bottom_right),
                )

    def draw(self, canvas: Canvas) -> None:
        if self.orientation == Line.Orientation.HORIZONTAL:
            self._draw_horizontal(canvas)
        else:
            self._draw_vertical(canvas)

    def serialize(self) -> Dict[str, Any]:
        data = super().serialize()
        data.update({"orientation": self.orientation})
        data.update({"is_arrow": self.is_arrow})
        return data

    def deserialize(self, data: Dict[str, Any]) -> None:
        super().deserialize(data)
        self.orientation = data["orientation"]
        self.is_arrow = data["is_arrow"]


class Designer:
    canvas: Canvas
    stdscr: curses.window
    status_bar: StatusBar
    objects: List[DiagramObject]
    selected_object_index: int
    cursor: Point
    cursor_mode: CursorMode
    key_bindings: Dict[int, Callable]
    sticky_mode: bool

    def __init__(
        self,
        stdscr: curses.window,
        window: curses.window,
        status_bar: StatusBar,
    ):
        # Turn off cursor blinking
        curses.curs_set(0)

        # Setup colors
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_YELLOW)

        self.stdscr = stdscr
        self.canvas = Canvas(window)
        self.status_bar = status_bar
        self.selected_object_index = -1
        self.cursor = Point(0, 0)
        self.cursor_mode = CursorMode.HAND
        self.objects = []
        self.key_bindings = self._get_key_bindings()
        self.sticky_mode = True

    @property
    def selected_object(self):
        if 0 <= self.selected_object_index < len(self.objects):
            return self.objects[self.selected_object_index]
        return None

    def _find_lines(self) -> Iterable[Line]:
        for obj in self.objects:
            if isinstance(obj, Line):
                yield cast(Line, obj)

    def _get_connected_lines(self) -> Tuple[List[Line], List[Line]]:
        starting_connected_lines: List[Line] = []
        ending_connected_lines: List[Line] = []
        if self.selected_object is None:
            return starting_connected_lines, ending_connected_lines
        # Move arrows too if they're connected
        if not isinstance(self.selected_object, Line):
            box = self.selected_object
            for arrow in self._find_lines():
                # Is the start of the arrow connected to the box?
                is_start_connected = arrow.top_left.is_within(
                    box.top_left - Size(1, 1), box.bottom_right + Size(1, 1)
                )
                # Is the end of the arrow connected to the box?
                is_end_connected = arrow.bottom_right.is_within(
                    box.top_left - Size(1, 1), box.bottom_right + Size(1, 1)
                )
                if is_start_connected:
                    starting_connected_lines.append(arrow)
                elif is_end_connected:
                    ending_connected_lines.append(arrow)
        return starting_connected_lines, ending_connected_lines

    def _on_cursor_move(self, dx: int, dy: int) -> None:
        if self.sticky_mode:
            starting_connected_arrows, ending_connected_arrows = (
                self._get_connected_lines()
            )

        max_x, max_y = self.canvas.getmaxxy()
        if self.selected_object:
            self.selected_object.position.x += dx
            self.selected_object.position.y += dy

            if self.sticky_mode:
                # Move connected arrows too
                for arrow in starting_connected_arrows:
                    arrow.position.x += dx
                    arrow.position.y += dy
                    # Without moving the end of it:
                    arrow.size.w -= dx
                    arrow.size.h -= dy
                # Move the end of the arrows
                for arrow in ending_connected_arrows:
                    arrow.size.w += dx
                    arrow.size.h += dy
        else:
            if 0 <= self.cursor.x + dx < max_x:
                self.cursor.x += dx
            if 0 <= self.cursor.y + dy < max_y:
                self.cursor.y += dy

    def _on_cursor_move_resize(self, dx: int, dy: int):
        if self.selected_object:
            self.selected_object.size.w += dx
            self.selected_object.size.h += dy

    def _on_switch_object(self, reverse: bool):
        next_cursor_mode = CursorMode.MOVE

        # Rotate selection
        if reverse:
            if self.selected_object_index == -1:
                self.selected_object_index = len(self.objects) - 1
            else:
                self.selected_object_index = self.selected_object_index - 1
            # Switch to hand mode if we cycled
            if self.selected_object_index < 0:
                next_cursor_mode = CursorMode.HAND
        else:
            self.selected_object_index = self.selected_object_index + 1
            # Switch to hand mode if we cycled
            if self.selected_object_index >= len(self.objects):
                self.selected_object_index = -1
                next_cursor_mode = CursorMode.HAND

        self.cursor_mode = next_cursor_mode

    def _set_selected_object(self, obj: DiagramObject) -> None:
        try:
            self.selected_object_index = self.objects.index(obj)
        except ValueError:
            pass

    def _get_new_obj_position(self, new_obj_width: int = 0) -> Point:
        """Find the best position for new objects."""
        if self.selected_object:
            if isinstance(self.selected_object, Line):
                if self.selected_object.orientation == Line.Orientation.HORIZONTAL:
                    size = Size(-(new_obj_width // 2), 1)
                else:
                    size = Size(1, self.selected_object.size.h // 2)
                return self.selected_object.bottom_right + size
            else:
                return self.selected_object.top_right + Size(
                    1, self.selected_object.size.h // 2
                )
        else:
            return copy(self.cursor)

    def draw(self) -> None:
        for object in self.objects:
            if object == self.selected_object:
                self.canvas.set_color(1)
            object.draw(self.canvas)
            if object == self.selected_object:
                self.canvas.reset_color()

        if not self.selected_object:
            self.canvas.put_ch(
                self.cursor,
                self.canvas.get_ch(self.cursor),
                curses.color_pair(1),
            )

    ##################
    # Commands
    ##################

    def _move_cursor_up(self) -> None:
        self._on_cursor_move(0, -1)

    def _move_cursor_down(self) -> None:
        self._on_cursor_move(0, 1)

    def _move_cursor_left(self) -> None:
        self._on_cursor_move(-1, 0)

    def _move_cursor_right(self) -> None:
        self._on_cursor_move(1, 0)

    def _add_box(self) -> None:
        self.objects.append(Box(self._get_new_obj_position(14), Size(14, 2)))
        self.selected_object_index = len(self.objects) - 1

    def _add_arrow(self) -> None:
        self.objects.append(Line(self._get_new_obj_position(), True, Size(6, 3)))
        self.selected_object_index = len(self.objects) - 1

    def _add_line(self) -> None:
        self.objects.append(Line(self._get_new_obj_position(), False, Size(6, 3)))
        self.selected_object_index = len(self.objects) - 1

    def _delete_cur_object(self) -> None:
        if 0 <= self.selected_object_index < len(self.objects):
            self.objects.pop(self.selected_object_index)
            self.selected_object_index -= 1

    def _unselect_cur_object(self) -> None:
        self.selected_object_index = -1

    def _select_or_edit_object_under_cursor(self) -> None:
        if self.selected_object is None:
            # Select the object on the cursor
            for i, obj in enumerate(self.objects):
                if self.cursor.is_within(obj.top_left, obj.bottom_right):
                    self.selected_object_index = i
        else:
            if hasattr(self.selected_object, "edit"):
                self.selected_object.edit(self.canvas)

    def _toggle_object(self) -> None:
        if hasattr(self.selected_object, "toggle"):
            self.selected_object.toggle()

    def _toggle_sticky_mode(self) -> None:
        self.sticky_mode = not self.sticky_mode

    def save(self, file_name: Optional[str] = None) -> None:
        if file_name is None:
            file_name = self.status_bar.input("File name to save:")
        if file_name.strip() == "":
            return
        objects = self.serialize()
        with open(file_name, "w") as file:
            json.dump(objects, file)

    def open(self, file_name: Optional[str] = None) -> None:
        if file_name is None:
            file_name = self.status_bar.input("File name to open:")
        if file_name == "" or not os.path.exists(file_name):
            self.status_bar.message("File not found.", curses.color_pair(2))
            return
        with open(file_name, "r") as file:
            objects = json.load(file)
            self.deserialize(objects)

    ##################
    # End of commands
    ##################

    def _get_key_bindings(self) -> Dict[int, Callable]:
        move_up = lambda: self._on_cursor_move(0, -1)  # noqa: E731
        move_down = lambda: self._on_cursor_move(0, 1)  # noqa: E731
        move_left = lambda: self._on_cursor_move(-1, 0)  # noqa: E731
        move_right = lambda: self._on_cursor_move(1, 0)  # noqa: E731
        resize_up = lambda: self._on_cursor_move_resize(0, -1)  # noqa: E731
        resize_down = lambda: self._on_cursor_move_resize(0, 1)  # noqa: E731
        resize_left = lambda: self._on_cursor_move_resize(-1, 0)  # noqa: E731
        resize_right = lambda: self._on_cursor_move_resize(1, 0)  # noqa: E731

        return {
            curses.KEY_UP: move_up,
            ord("k"): move_up,
            curses.KEY_DOWN: move_down,
            ord("j"): move_down,
            curses.KEY_LEFT: move_left,
            ord("h"): move_left,
            curses.KEY_RIGHT: move_right,
            ord("l"): move_right,
            curses.KEY_SR: resize_up,
            ord("K"): resize_up,
            curses.KEY_SF: resize_down,
            ord("J"): resize_down,
            curses.KEY_SLEFT: resize_left,
            ord("H"): resize_left,
            curses.KEY_SRIGHT: resize_right,
            ord("L"): resize_right,
            curses.ascii.TAB: lambda: self._on_switch_object(reverse=False),
            curses.KEY_BTAB: lambda: self._on_switch_object(reverse=True),
            curses.ascii.ESC: self._unselect_cur_object,
            curses.ascii.NL: self._select_or_edit_object_under_cursor,
            curses.ascii.SP: self._toggle_object,
            ord("s"): self.save,
            ord("o"): self.open,
            ord("b"): self._add_box,
            ord("a"): self._add_arrow,
            ord("c"): self._add_line,
            ord("d"): self._delete_cur_object,
            ord("t"): self._toggle_sticky_mode,
        }

    def _update_status_bar(self) -> None:
        self.status_bar.set_shortcut(
            "Enter",
            "Edit" if self.selected_object else "Select",
        )
        self.status_bar.set_shortcut(
            "T",
            "Sticky" if self.sticky_mode else "Nonsticky",
        )
        self.status_bar.invalidate()

    def _confirm_exit(self) -> bool:
        res = self.status_bar.message(
            "Quit? [y/N]",
            curses.color_pair(4),
        )
        return chr(res).lower() == "y"

    def loop(self):
        while True:
            try:
                self.canvas.clear()
                self.draw()
                self.canvas.refresh()
                self._update_status_bar()

                key = self.canvas.read_keyboard_ch()
                if key == ord("q") and self._confirm_exit():
                    break

                if key == curses.KEY_RESIZE:
                    self.status_bar.resize()
                    self.canvas.resize(self.stdscr)
                    continue

                command = self.key_bindings.get(key)
                if command:
                    command()
            except KeyboardInterrupt:
                # Need to read Ctrl+C first
                self.canvas.read_keyboard_ch()
                if self._confirm_exit():
                    break

    def serialize(self) -> List[Dict[str, Any]]:
        serialized = []
        for object in self.objects:
            serialized.append(object.serialize())
        return serialized

    def deserialize(self, items: List[Dict[str, Any]]) -> None:
        self.selected_object_index = -1
        self.objects.clear()
        for item in items:
            type_name = item["type"]
            klass = globals()[type_name]
            obj = klass()
            obj.deserialize(item)
            self.objects.append(obj)

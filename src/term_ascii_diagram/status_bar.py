import curses
from collections import OrderedDict
from curses.textpad import Textbox
from typing import Dict, Optional


class StatusBar:
    bg_color: int
    shortcuts: Dict[str, str]
    root_window: curses.window
    window: curses.window

    def __init__(
        self,
        root_window: curses.window,
        window: curses.window,
        bg_color: int,
    ):
        self.root_window = root_window
        self.window = window
        self.bg_color = bg_color
        self.shortcuts = OrderedDict()

    def set_shortcut(self, key: str, label: str) -> None:
        self.shortcuts[key] = label

    def input(self, prompt: str) -> str:
        _, max_x = self.window.getmaxyx()
        root_max_y, _ = self.root_window.getmaxyx()
        prompt = prompt[: max_x - 1]
        self.window.addstr(0, 0, prompt, self.bg_color)
        self.window.addstr(0, len(prompt), " " * (max_x - len(prompt) - 1))
        curses.curs_set(1)
        edit_win = curses.newwin(
            1,
            0,
            root_max_y - 1,
            len(prompt),
        )
        box = Textbox(edit_win, insert_mode=True)
        self.window.refresh()
        try:
            result = box.edit().strip()
        except KeyboardInterrupt:
            result = ""
        curses.curs_set(0)
        self.invalidate()
        return result

    def message(self, text: str, attr: Optional[int] = None) -> int:
        _, max_x = self.window.getmaxyx()
        self.window.addstr(
            0,
            0,
            text + (" " * (max_x - len(text) - 1)),
            attr or self.bg_color,
        )
        return self.window.getch()

    def resize(self) -> None:
        max_y, max_x = self.root_window.getmaxyx()
        self.window.resize(1, max_x)
        self.window.mvwin(max_y - 1, 0)

    def invalidate(self):
        _, max_x = self.window.getmaxyx()
        self.window.addstr(0, 0, " " * (max_x - 1), self.bg_color)
        x = 0
        try:
            for key, label in self.shortcuts.items():
                self.window.addstr(0, x, key)
                x += len(key)
                self.window.addstr(0, x, label, self.bg_color)
                x += len(label) + 1
                if x >= max_x:
                    break
        except curses.error:
            # When the screen is small we get an exception for the last items
            pass
        self.window.refresh()

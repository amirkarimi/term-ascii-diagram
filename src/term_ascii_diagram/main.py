import argparse
import curses
import curses.ascii
import os

from term_ascii_diagram.diagram import Designer
from term_ascii_diagram.status_bar import StatusBar


def wrapped(args):
    def main(stdscr: curses.window):
        stdscr.keypad(True)
        max_y, max_x = stdscr.getmaxyx()

        # Status bar
        status_bar_window = stdscr.subwin(1, max_x, max_y - 1, 0)
        status_bar = StatusBar(stdscr, status_bar_window, curses.color_pair(3))
        status_bar.set_shortcut("Q", "uit")
        status_bar.set_shortcut("S", "ave")
        status_bar.set_shortcut("O", "pen")
        status_bar.set_shortcut("B", "ox")
        status_bar.set_shortcut("A", "rrow")
        status_bar.set_shortcut("C", "onnection")
        status_bar.set_shortcut("D", "elete")
        status_bar.set_shortcut("T", "Sticky")
        status_bar.set_shortcut("Tab", "Next")
        status_bar.set_shortcut("Enter", "Select/Edit")
        status_bar.set_shortcut("Shift", "Resize")
        status_bar.set_shortcut("Spc", "Toggle")
        status_bar.invalidate()

        # Main window
        main_window = stdscr.subwin(max_y - 1, max_x, 0, 0)
        main_window.keypad(True)

        # Initialize the designer
        designer = Designer(stdscr, main_window, status_bar)
        if args.filename:
            designer.open(args.filename)

        designer.loop()

    return main


def cli():
    parser = argparse.ArgumentParser(
        prog="term-ascii-diagram",
        description="Terminal ASCII Diagram Builder.",
    )

    parser.add_argument("filename", nargs="?")
    parser.add_argument("-r", "--render")

    args = parser.parse_args()

    # To support escape key press
    os.environ.setdefault("ESCDELAY", "25")
    # Initialize curses
    curses.wrapper(wrapped(args))


if __name__ == "__main__":
    cli()

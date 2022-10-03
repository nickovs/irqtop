#!/usr/bin/env python3
"""A top-like tool for displaying IRQ activity"""

# Copyright (C) Nicko van Someren, 2022

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import os
import re
import dataclasses
import select
import sys
import time
import termios
import fcntl
from typing import List, Dict


class UnbufferedTerminal:
    """A context manager which switches a terminal to non-blocking,
    non-buffered, non-echoed mode while in effect"""
    def __init__(self, fh=None, inverted=False):
        self._in_file = sys.stdin if fh is None else fh
        self._in_file_no = self._in_file.fileno()
        self._inverted = inverted

    def __enter__(self):
        file_no = self._in_file_no

        self._old_term = termios.tcgetattr(file_no)
        new_attr = termios.tcgetattr(file_no)
        if not self._inverted:
            new_attr[3] = new_attr[3] & ~termios.ICANON & ~termios.ECHO
        else:
            new_attr[3] = new_attr[3] | termios.ICANON | termios.ECHO
        termios.tcsetattr(file_no, termios.TCSANOW, new_attr)

        self._old_flags = fcntl.fcntl(file_no, fcntl.F_GETFL)
        if not self._inverted:
            fcntl.fcntl(file_no, fcntl.F_SETFL, self._old_flags | os.O_NONBLOCK)
        else:
            fcntl.fcntl(file_no, fcntl.F_SETFL, self._old_flags & ~os.O_NONBLOCK)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        termios.tcsetattr(self._in_file_no, termios.TCSAFLUSH, self._old_term)
        fcntl.fcntl(self._in_file_no, fcntl.F_SETFL, self._old_flags)

        if exc_type == KeyboardInterrupt:
            return True

    def get_chr(self, timeout=0):
        if self._inverted:
            raise NotImplementedError("get_chr() is not available in cooked mode")

        [rd, _, _] = select.select([self._in_file_no], [], [], timeout)
        if rd:
            return self._in_file.read(1)
        return None

    def suspend(self):
        """Return a context handler that temporarily suspends the effect of this one"""
        return UnbufferedTerminal(self._in_file, not self._inverted)


@dataclasses.dataclass
class IRQCount:
    name: str
    total: int
    counts: List[int]
    comment: str


class IRQTop:
    """A class to record and update IRQ counts and their first order differential"""
    _cpu_count: int
    _last_readings: Dict[str, IRQCount]
    _last_deltas: Dict[str, IRQCount]

    def __init__(self):
        self._fh = open("/proc/interrupts")
        self._cpu_count = -1
        self._last_readings = {}
        self._last_deltas = {}

    def _irq_delta(self, new_value: IRQCount):
        if new_value.name in self._last_readings:
            old_value = self._last_readings[new_value.name]
            total_d = new_value.total - old_value.total
            counts_d = [new_value.counts[i] - old_value.counts[i] for i in range(len(new_value.counts))]
            return IRQCount(new_value.name, total_d, counts_d, new_value.comment)
        else:
            return new_value

    @staticmethod
    def parse_line(line, last_cpu_col):
        parts = line[:last_cpu_col].split()
        irq_id = parts[0].strip(":")
        try:
            counts = list(map(int, parts[1:]))
        except ValueError:
            counts = []
        total = sum(counts)
        tail_parts = line[last_cpu_col:].strip().split("  ")
        source = tail_parts[-1].strip()
        return IRQCount(irq_id, total, counts, source)

    def _read_irq_data(self):
        self._fh.seek(0)
        lines = self._fh.readlines()

        cpu_line = lines[0].rstrip()
        last_cpu_col = len(cpu_line)
        self._cpu_count = len(cpu_line.split())

        raw_readings = [self.parse_line(line, last_cpu_col) for line in lines[1:]]
        mapped_readings = dict((i.name, i) for i in raw_readings)
        delta_readings = dict((name, self._irq_delta(value)) for name, value in mapped_readings.items())

        self._last_readings = mapped_readings
        self._last_deltas = delta_readings

    def poll(self) -> Dict[str, IRQCount]:
        self._read_irq_data()
        return self._last_deltas

    @property
    def cpu_count(self):
        return self._cpu_count


def _cpu_list_split(cpus):
    parts = cpus.split(",")
    r = []
    for part in parts:
        part = part.strip()
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            r.extend(range(start, end+1))
        else:
            r.append(int(part))
    return r


def _lax_max(items):
    items = list(items)
    return max(items) if items else 0


def _pad_numeric(name):
    name = name.strip()
    if name.isdigit():
        name = ("0" * 9 + name)[-10:]
    return name


_sort_keys = {
    "T": (lambda irq: irq.total, False),
    "t": (lambda irq: irq.total, True),
    "n": (lambda irq: _pad_numeric(irq.name), False),
    "N": (lambda irq: _pad_numeric(irq.name), True),
    "d": (lambda irq: irq.comment, False),
    "D": (lambda irq: irq.comment, True),
}


def positive_int(arg_str):
    value = int(arg_str)
    if value < 0:
        raise argparse.ArgumentTypeError('value must be positive')
    return value


def flash_message(m):
    print(m)
    time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description='Display the top sources of interrupts')
    parser.add_argument("--filter", "-f", metavar="REGEX", default=None,
                        type=str, help="Only display IRQ sources matching regex")
    parser.add_argument("--interval", "-i", metavar="N", default=1.0,
                        type=float, help="Sample every N seconds")
    parser.add_argument("--count", "-n", metavar="N", default=0, type=positive_int,
                        help="Update the results N times and then exit")
    parser.add_argument("--total", "-t", action='store_true',
                        default=None, help="Only display the total count, not per CPU")
    parser.add_argument("--no-total", dest='total', action='store_false',
                        help="Hide the total IRQ count")
    parser.add_argument("--details", "--device", "-d", action='store_true',
                        default=None, help="Force display of device details")
    parser.add_argument("--no-details", "--no-device", dest="details", action="store_false",
                        help="Hide the device details")
    parser.add_argument("--cpus", "-c", metavar="CPUS",
                        help="Display just listed CPUs (e.g. 0,1,5-7) and total")
    parser.add_argument("--sort", "-s", metavar="ORDER", default='t',
                        help="Sort by (t)otal count, (n)ame or (d)evice. Upper case to reverse order")

    args = parser.parse_args()

    filter_re = re.compile(args.filter) if args.filter is not None else None

    sorter, sort_reverse = None, False
    if args.sort in _sort_keys:
        sorter, sort_reverse = _sort_keys[args.sort]
    else:
        parser.exit(1, f"Unknown sort key: {args.sort}")

    cpus = None
    just_total = args.total is True

    if args.cpus is not None:
        cpus = _cpu_list_split(args.cpus)

    if just_total:
        cpus = []

    show_total = not(args.total is False)

    if sys.stdout.isatty():
        tty_width, tty_height = os.get_terminal_size()
        tty_height = max(tty_height, 3)
    else:
        tty_width, tty_height = -1, -1

    tracker = IRQTop()

    running = True

    details = args.details
    interval = args.interval

    count = args.count
    iteration = 0

    with UnbufferedTerminal() as unbuffered:
        while running and (count == 0 or iteration < count):
            iteration += 1
            t = time.time()
            deltas = tracker.poll()

            use_cpus = cpus if cpus is not None else list(range(tracker.cpu_count))

            if filter_re is not None:
                filtered = [value for name, value in deltas.items() if filter_re.search(name + value.comment)]
                if not filtered:
                    filtered = [IRQCount("No IRQs matching filter", 0, [], "")]
            else:
                filtered = list(deltas.values())

            filtered.sort(key=sorter, reverse=sort_reverse)

            if sys.stdout.isatty():
                tty_width, tty_height = os.get_terminal_size()
                tty_height = max(tty_height, 3)

            if tty_height != -1 and len(filtered) > tty_height - 2:
                filtered = filtered[:tty_height-2]

            name_width = max(len(i.name) for i in filtered)
            max_total = max(i.total for i in filtered)
            max_count = _lax_max(c
                                 for i in filtered if i.counts
                                 for n, c in enumerate(i.counts) if n in use_cpus)
            total_width = max(len(str(max_total)), 5)
            count_width = max(len(str(max_count)), 5)
            reserve_comment = min(max(len(i.comment) for i in filtered), tty_width // 3)

            if tty_width != -1:
                left_width = name_width + 1
                if show_total:
                    left_width += total_width + 1

                if details is True:
                    # If we are forcing the display of details, reserve a third of the width
                    left_width += reserve_comment

                if left_width > tty_width:
                    use_cpus = []
                else:
                    cpu_room = (tty_width - left_width) // (count_width + 1)
                    use_cpus = use_cpus[:cpu_room]
                    left_width += len(use_cpus) * (count_width + 1)

                if details is True:
                    left_width -= reserve_comment

                comment_width = (tty_width - left_width) - 1
                if details is False or comment_width < 6:
                    comment_width = 0
            else:
                comment_width = 255

            def format_line(name, total, counts, comment):
                line = name.rjust(name_width)
                if show_total:
                    line += " " + str(total).rjust(total_width)
                if not just_total:
                    line += " " + " ".join(str(c).rjust(count_width) for c in counts)
                line += " " + comment[:comment_width]
                return line

            print('\x0c')
            print(format_line("", "TOTAL", [f"CPU{i}" for i in use_cpus], ""))

            for row in filtered:
                print(format_line(row.name, row.total,
                                  [row.counts[i] for i in use_cpus if i < len(row.counts)],
                                  row.comment))

            next_refresh_time = t + interval

            while time.time() < next_refresh_time:
                wait = next_refresh_time - time.time()
                key = unbuffered.get_chr(wait)

                if key in ['q', 'Q', '\x1b']:
                    # Quit on q, Q or ESC
                    running = False
                    break
                elif key in ['s', 'S']:
                    # Change the sort order
                    with unbuffered.suspend():
                        keys = ''.join(_sort_keys.keys()) + '='
                        new_sort_key = input(f"Sort key ({keys}):")
                        if new_sort_key == '=':
                            frozen_order = dict((entry.name, i) for i, entry in enumerate(filtered))

                            def frozen_sorter_key(entry):
                                return frozen_order[entry.name] if entry.name in frozen_order else len(frozen_order)
                            sorter, sort_reverse = frozen_sorter_key, False
                        elif new_sort_key in _sort_keys:
                            sorter, sort_reverse = _sort_keys[new_sort_key]
                        else:
                            flash_message(f"Sort key must be one of: {keys}")
                elif key in ['f', 'F']:
                    # Filter the messages
                    with unbuffered.suspend():
                        new_filter = input("Enter filter expression:")
                        if new_filter:
                            try:
                                filter_re = re.compile(new_filter)
                            except re.error:
                                flash_message("Bad regular expression")
                        else:
                            filter_re = None
                            flash_message("Filter cleared")
                elif key in ['c', 'C']:
                    # Change the set of displayed CPUs
                    with unbuffered.suspend():
                        new_cpu_list = input("Enter list of CPUs:").strip()
                        if new_cpu_list == '-':
                            cpus = []
                        elif new_cpu_list == '+':
                            cpus = None
                        if new_cpu_list:
                            try:
                                cpus = _cpu_list_split(new_cpu_list)
                            except ValueError:
                                flash_message("Bad CPU list")
                        else:
                            cpus = [] if just_total else None
                elif key == 't':
                    # Toggle total display
                    show_total = not show_total
                elif key == 'd':
                    # Toggle details display
                    details = (comment_width == 0)
                elif key == 'D':
                    # Display details only if there is space
                    details = None
                elif key == 'i':
                    # Change the sampling interval
                    with unbuffered.suspend():
                        new_interval = input("Refresh interval (seconds):").strip()
                        if new_interval:
                            try:
                                interval = float(new_interval.strip())
                            except ValueError:
                                flash_message("Interval value must be a number")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Working-day timeline for Plane tasks: skips Saturday, Sunday and VN public holidays.

    workdays.py plan <hotfix|bug|small|large|N> [--start YYYY-MM-DD]
    workdays.py check <start YYYY-MM-DD> <due YYYY-MM-DD>

The start day counts as day 1. Holidays come from ../references/vn-holidays.txt.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

HOLIDAYS_FILE = Path(__file__).resolve().parent.parent / "references" / "vn-holidays.txt"
SIZES = {"hotfix": 1, "bug": 2, "small": 3, "large": 5}
ONE_DAY = dt.timedelta(days=1)


def load_holidays():
    """Return {date: note} parsed from the holidays file."""
    holidays = {}
    for line in HOLIDAYS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        date_text, _, note = line.partition(" ")
        holidays[dt.date.fromisoformat(date_text)] = note.strip()
    return holidays


HOLIDAYS = load_holidays()


def is_workday(day):
    return day.weekday() < 5 and day not in HOLIDAYS


def next_workday(day):
    while not is_workday(day):
        day += ONE_DAY
    return day


def add_workdays(start, count):
    """Return the due date of a task of `count` working days starting on `start`."""
    day, left = start, count - 1
    while left:
        day += ONE_DAY
        left -= is_workday(day)
    return day


def label(day):
    return f"{day.isoformat()} ({day.strftime('%a')})"


def skipped_days(start, due):
    """List the non-working days inside [start, due] with the reason."""
    day, skipped = start, []
    while day <= due:
        if day in HOLIDAYS:
            skipped.append(f"{label(day)} {HOLIDAYS[day]}")
        elif day.weekday() >= 5:
            skipped.append(label(day))
        day += ONE_DAY
    return skipped


def count_workdays(start, due):
    return sum(is_workday(start + ONE_DAY * offset) for offset in range((due - start).days + 1))


def warn_unknown_years(start, due):
    known = {day.year for day in HOLIDAYS}
    missing = sorted(set(range(start.year, due.year + 1)) - known)
    if missing:
        print(f"WARNING no holiday data for {missing}: update references/vn-holidays.txt")


def report(start, due):
    print(f"start    {label(start)}")
    print(f"due      {label(due)}")
    print(f"workdays {count_workdays(start, due)}")
    for line in skipped_days(start, due):
        print(f"skipped  {line}")
    warn_unknown_years(start, due)


def plan(args):
    count = SIZES.get(args.size) or int(args.size)
    if count > SIZES["large"]:
        print(f"NOTE {count} working days > {SIZES['large']}: split into sub-items")
    start = next_workday(args.start or dt.date.today())
    report(start, add_workdays(start, count))


def check(args):
    if args.due < args.start:
        sys.exit("ERROR due date is before start date")
    for name, day in (("start", args.start), ("due", args.due)):
        if not is_workday(day):
            print(f"INVALID {name} {label(day)} is not a working day -> next {label(next_workday(day))}")
    report(args.start, args.due)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan", help="suggest start/due from a size or a number of working days")
    plan_parser.add_argument("size", help="hotfix=1, bug=2, small=3, large=5, or a number of working days")
    plan_parser.add_argument("--start", type=dt.date.fromisoformat, help="first possible day (default today)")
    plan_parser.set_defaults(handler=plan)
    check_parser = commands.add_parser("check", help="validate a given start/due pair")
    check_parser.add_argument("start", type=dt.date.fromisoformat)
    check_parser.add_argument("due", type=dt.date.fromisoformat)
    check_parser.set_defaults(handler=check)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()

"""python3 -m report [--by-month] <file>  (.csv, .json, .xlsx or .xml)"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from report.expenses import ReportError, monthly_totals, read_expenses, summary, totals_by_currency

USAGE = "usage: python3 -m report [--by-month] <file>  (.csv, .json, .xlsx or .xml)"


def format_by_month(totals: dict[str, dict[str, Decimal]]) -> str:
    if not totals:
        return "No expenses."
    blocks = []
    for month in sorted(totals):
        lines = [f"  {cur} {amount}" for cur, amount in sorted(totals[month].items())]
        blocks.append("\n".join([month, *lines]))
    return "\n\n".join(blocks)


def main(argv: list[str]) -> int:
    flags = [a for a in argv if a.startswith("--")]
    paths = [a for a in argv if not a.startswith("--")]
    if len(paths) != 1 or any(f != "--by-month" for f in flags):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        expenses = read_expenses(Path(paths[0]))
    except (OSError, ReportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if flags:
        print(format_by_month(monthly_totals(expenses)))
        return 0
    print(summary(expenses))
    for line in totals_by_currency(expenses):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

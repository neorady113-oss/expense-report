"""Read expenses from a CSV file (date,description,amount,currency) and summarise them."""

from __future__ import annotations

import csv
import json
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path


XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


@dataclass(frozen=True)
class Expense:
    day: date
    description: str
    amount: Decimal
    currency: str


class ReportError(ValueError):
    """A row the report cannot use; the message names its line in the file."""


def parse_row(row: dict[str, str], line: int) -> Expense:
    try:
        day = date.fromisoformat(row["date"].strip())
        amount = Decimal(row["amount"].strip())
    except (KeyError, AttributeError, ValueError, InvalidOperation) as exc:
        raise ReportError(f"line {line}: cannot read date or amount ({exc})") from exc
    currency = (row.get("currency") or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ReportError(f"line {line}: currency must be a 3-letter code, got {currency!r}")
    return Expense(day, (row.get("description") or "").strip(), amount, currency)


def read_csv(path: Path) -> list[Expense]:
    with path.open(newline="", encoding="utf-8") as f:
        return [parse_row(row, n) for n, row in enumerate(csv.DictReader(f), start=2)]


def read_json(path: Path) -> list[Expense]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    except ValueError as exc:
        raise ReportError(f"invalid JSON ({exc})") from exc
    if not isinstance(data, list):
        raise ReportError("invalid JSON: expected a top-level array of objects")
    expenses = []
    for n, item in enumerate(data, start=2):
        if not isinstance(item, dict):
            raise ReportError(f"line {n}: expected an object")
        expenses.append(parse_row({k: "" if v is None else str(v) for k, v in item.items()}, n))
    return expenses


def read_xml(path: Path) -> list[Expense]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ReportError(f"invalid XML ({exc})") from exc
    rows = [{c.tag: c.text or "" for c in item} for item in root.findall("expense")]
    return [parse_row(row, n) for n, row in enumerate(rows, start=2)]


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{XLSX_NS}}}t"))
    value = cell.findtext(f"{{{XLSX_NS}}}v") or ""
    return shared[int(value)] if kind == "s" else value


def _xlsx_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        sst = ET.fromstring(z.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in names else None
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    shared = ["".join(t.text or "" for t in si.iter(f"{{{XLSX_NS}}}t")) for si in sst] if sst is not None else []
    rows = []
    for row in sheet.iter(f"{{{XLSX_NS}}}row"):
        cells = {c.get("r", "").rstrip("0123456789"): _cell_text(c, shared) for c in row}
        rows.append(cells)
    return rows


def read_xlsx(path: Path) -> list[Expense]:
    try:
        rows = _xlsx_rows(path)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, IndexError) as exc:
        raise ReportError(f"invalid xlsx file ({exc})") from exc
    if not rows:
        return []
    header = rows[0]
    return [parse_row({name: row.get(col, "") for col, name in header.items()}, n)
            for n, row in enumerate(rows[1:], start=2)]


READERS = {".csv": read_csv, ".json": read_json, ".xlsx": read_xlsx, ".xml": read_xml}


def read_expenses(path: Path) -> list[Expense]:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ReportError(f"unsupported file format {path.suffix!r} (use .csv, .json, .xlsx or .xml)")
    return reader(path)


def totals_by_currency(expenses: list[Expense]) -> list[str]:
    totals: dict[str, Decimal] = {}
    for e in expenses:
        totals[e.currency] = totals.get(e.currency, Decimal(0)) + e.amount
    cent = Decimal("0.01")
    return [f"{code} {total.quantize(cent, rounding=ROUND_HALF_UP)}" for code, total in sorted(totals.items())]


def monthly_totals(expenses: list[Expense]) -> dict[str, dict[str, Decimal]]:
    raw: dict[str, dict[str, Decimal]] = {}
    for e in expenses:
        month = raw.setdefault(e.day.strftime("%Y-%m"), {})
        month[e.currency] = month.get(e.currency, Decimal(0)) + e.amount
    return {m: dict(sorted(raw[m].items())) for m in sorted(raw)}


def summary(expenses: list[Expense]) -> str:
    if not expenses:
        return "No expenses."
    days = sorted(e.day for e in expenses)
    return f"{len(expenses)} expenses from {days[0].isoformat()} to {days[-1].isoformat()}"

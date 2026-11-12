import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from report.__main__ import format_by_month
from report.expenses import (
    Expense,
    ReportError,
    monthly_totals,
    parse_row,
    read_expenses,
    summary,
    totals_by_currency,
)

ROW = {"date": "2026-10-03", "description": "Taxi", "amount": "12.50", "currency": "usd"}


def write_csv(text: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return Path(f.name)


class ParseRow(unittest.TestCase):
    def test_reads_a_row(self) -> None:
        self.assertEqual(parse_row(ROW, 2), Expense(date(2026, 10, 3), "Taxi", Decimal("12.50"), "USD"))

    def test_bad_date_names_the_line(self) -> None:
        with self.assertRaisesRegex(ReportError, "line 7"):
            parse_row({**ROW, "date": "03/10/2026"}, 7)

    def test_bad_amount(self) -> None:
        with self.assertRaises(ReportError):
            parse_row({**ROW, "amount": "twelve"}, 2)

    def test_bad_currency(self) -> None:
        with self.assertRaisesRegex(ReportError, "3-letter"):
            parse_row({**ROW, "currency": "dollars"}, 2)


class ReadAndSummarise(unittest.TestCase):
    def test_reads_a_file(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-03,Taxi,12.50,USD\n2026-10-05,Lunch,9,EUR\n")
        self.assertEqual([e.currency for e in read_expenses(path)], ["USD", "EUR"])

    def test_error_line_counts_the_header(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-03,Taxi,x,USD\n")
        with self.assertRaisesRegex(ReportError, "line 2"):
            read_expenses(path)

    def test_summary(self) -> None:
        expenses = [parse_row(ROW, 2), parse_row({**ROW, "date": "2026-09-30"}, 3)]
        self.assertEqual(summary(expenses), "2 expenses from 2026-09-30 to 2026-10-03")

    def test_summary_of_nothing(self) -> None:
        self.assertEqual(summary([]), "No expenses.")


def cur_exp(amount: str, currency: str) -> Expense:
    return Expense(date(2026, 10, 3), "x", Decimal(amount), currency)


class Totals(unittest.TestCase):
    def test_sums_per_currency(self) -> None:
        self.assertEqual(totals_by_currency([cur_exp("12.50", "USD"), cur_exp("7.50", "USD")]), ["USD 20.00"])

    def test_sorted_by_code(self) -> None:
        got = totals_by_currency([cur_exp("1", "USD"), cur_exp("2", "EUR"), cur_exp("3", "COP")])
        self.assertEqual(got, ["COP 3.00", "EUR 2.00", "USD 1.00"])

    def test_decimal_precision(self) -> None:
        self.assertEqual(totals_by_currency([cur_exp("0.10", "EUR"), cur_exp("0.20", "EUR")]), ["EUR 0.30"])
        self.assertEqual(totals_by_currency([cur_exp("9", "EUR")]), ["EUR 9.00"])

    def test_empty(self) -> None:
        self.assertEqual(totals_by_currency([]), [])


def exp(day: str, amount: str, cur: str = "USD") -> Expense:
    return Expense(date.fromisoformat(day), "x", Decimal(amount), cur)


class MonthlyTotals(unittest.TestCase):
    def test_sums_decimal_per_month(self) -> None:
        result = monthly_totals([exp("2026-10-01", "0.10"), exp("2026-10-02", "0.20")])
        self.assertEqual(result, {"2026-10": {"USD": Decimal("0.30")}})

    def test_keeps_currencies_separate(self) -> None:
        result = monthly_totals([exp("2026-10-01", "1", "USD"), exp("2026-10-02", "2", "EUR")])
        self.assertEqual(result["2026-10"], {"EUR": Decimal("2"), "USD": Decimal("1")})
        self.assertEqual(list(result["2026-10"]), ["EUR", "USD"])

    def test_months_are_chronological(self) -> None:
        result = monthly_totals([exp("2026-01-05", "1"), exp("2025-12-31", "1")])
        self.assertEqual(list(result), ["2025-12", "2026-01"])

    def test_empty(self) -> None:
        self.assertEqual(monthly_totals([]), {})


class FormatByMonth(unittest.TestCase):
    def test_blocks(self) -> None:
        data = {
            "2026-09": {"EUR": Decimal("9.00"), "USD": Decimal("30.00")},
            "2026-10": {"USD": Decimal("12.50")},
        }
        expected = "2026-09\n  EUR 9.00\n  USD 30.00\n\n2026-10\n  USD 12.50"
        self.assertEqual(format_by_month(data), expected)

    def test_sorts_currencies(self) -> None:
        text = format_by_month({"2026-09": {"USD": Decimal("1"), "EUR": Decimal("2")}})
        self.assertEqual(text, "2026-09\n  EUR 2\n  USD 1")

    def test_empty(self) -> None:
        self.assertEqual(format_by_month({}), "No expenses.")


CSV_TEXT = (
    "date,description,amount,currency\n"
    "2026-10-03,Taxi,12.50,USD\n"
    "2026-09-05,Lunch,9,EUR\n"
    "2026-09-06,Hotel,30.00,USD\n"
)
BY_MONTH_EXPECTED = "2026-09\n  EUR 9\n  USD 30.00\n\n2026-10\n  USD 12.50\n"


class CliByMonth(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_flag_before_path(self) -> None:
        out = self.run_cli("--by-month", str(write_csv(CSV_TEXT)))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.replace("\r\n", "\n"), BY_MONTH_EXPECTED)

    def test_flag_after_path(self) -> None:
        out = self.run_cli(str(write_csv(CSV_TEXT)), "--by-month")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.replace("\r\n", "\n"), BY_MONTH_EXPECTED)

    def test_without_flag_unchanged(self) -> None:
        out = self.run_cli(str(write_csv(CSV_TEXT)))
        self.assertIn("expenses from", out.stdout)

    def test_bad_row_exits_1(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-03,Taxi,x,USD\n")
        out = self.run_cli("--by-month", str(path))
        self.assertEqual(out.returncode, 1)
        self.assertIn("line 2", out.stderr)

    def test_unknown_flag_exits_2(self) -> None:
        self.assertEqual(self.run_cli("--nope", "data/sample.csv").returncode, 2)


class Cli(unittest.TestCase):
    def test_prints_totals(self) -> None:
        path = write_csv(
            "date,description,amount,currency\n2026-10-03,Taxi,12.50,usd\n"
            "2026-10-05,Lunch,9,EUR\n2026-10-06,Bus,7.50,USD\n"
        )
        out = self.run_cli(str(path))
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        self.assertIn("expenses from", lines[0])
        self.assertEqual(lines[1:], ["EUR 9.00", "USD 20.00"])

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_prints_the_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("expenses from", out.stdout)

    def test_bad_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("missing.csv").returncode, 1)


NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
EXPECTED = [
    Expense(date(2026, 10, 3), "Taxi", Decimal("12.50"), "USD"),
    Expense(date(2026, 10, 5), "Lunch", Decimal("9"), "EUR"),
]


def write_file(name: str, text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / name
    path.write_text(text, encoding="utf-8")
    return path


def json_text(amount: str = "12.50", day: str = "2026-10-03") -> str:
    return (
        '[{"date": "%s", "description": "Taxi", "amount": %s, "currency": "USD"},'
        ' {"date": "2026-10-05", "description": "Lunch", "amount": 9, "currency": "EUR"}]' % (day, amount)
    )


def xml_text(amount: str = "<amount>12.50</amount>") -> str:
    return (
        "<expenses><expense><date>2026-10-03</date><description>Taxi</description>"
        f"{amount}<currency>USD</currency></expense>"
        "<expense><date>2026-10-05</date><description>Lunch</description>"
        "<amount>9</amount><currency>EUR</currency></expense></expenses>"
    )


def write_xlsx(amount: str = "12.5", day: str = "2026-10-03") -> Path:
    import zipfile

    strings = ["date", "description", "amount", "currency", day, "Taxi", "USD", "2026-10-05", "Lunch", "EUR"]
    sst = f'<sst xmlns="{NS}">' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>"

    def s(ref: str, i: int) -> str:
        return f'<c r="{ref}" t="s"><v>{i}</v></c>'

    sheet = (
        f'<worksheet xmlns="{NS}"><sheetData>'
        f"<row r=\"1\">{s('A1', 0)}{s('B1', 1)}{s('C1', 2)}{s('D1', 3)}</row>"
        f"<row r=\"2\">{s('A2', 4)}{s('B2', 5)}<c r=\"C2\"><v>{amount}</v></c>{s('D2', 6)}</row>"
        f"<row r=\"3\">{s('A3', 7)}{s('B3', 8)}<c r=\"C3\"><v>9</v></c>{s('D3', 9)}</row>"
        "</sheetData></worksheet>"
    )
    path = Path(tempfile.mkdtemp()) / "data.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/sharedStrings.xml", sst)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


class Formats(unittest.TestCase):
    def test_json(self) -> None:
        self.assertEqual(read_expenses(write_file("d.json", json_text())), EXPECTED)

    def test_json_bad_date_names_line(self) -> None:
        with self.assertRaisesRegex(ReportError, "line 2"):
            read_expenses(write_file("d.json", json_text(day="nope")))

    def test_json_invalid_or_not_array(self) -> None:
        with self.assertRaises(ReportError):
            read_expenses(write_file("d.json", "{not json"))
        with self.assertRaises(ReportError):
            read_expenses(write_file("d.json", "{}"))

    def test_xml(self) -> None:
        self.assertEqual(read_expenses(write_file("d.xml", xml_text())), EXPECTED)

    def test_xml_missing_amount_names_line(self) -> None:
        with self.assertRaisesRegex(ReportError, "line 2"):
            read_expenses(write_file("d.xml", xml_text(amount="")))

    def test_xml_malformed(self) -> None:
        with self.assertRaises(ReportError):
            read_expenses(write_file("d.xml", "<expenses>"))

    def test_xlsx(self) -> None:
        self.assertEqual(read_expenses(write_xlsx()), EXPECTED)

    def test_xlsx_bad_value_names_line(self) -> None:
        with self.assertRaisesRegex(ReportError, "line 2"):
            read_expenses(write_xlsx(day="bad"))

    def test_xlsx_not_a_zip(self) -> None:
        with self.assertRaises(ReportError):
            read_expenses(write_file("d.xlsx", "plain text"))

    def test_extension_case_insensitive(self) -> None:
        self.assertEqual(read_expenses(write_file("DATA.JSON", json_text())), EXPECTED)

    def test_unsupported_extension(self) -> None:
        for name in ("d.txt", "d.xls"):
            with self.assertRaisesRegex(ReportError, "unsupported"):
                read_expenses(write_file(name, "x"))

    def test_same_summary_in_all_formats(self) -> None:
        csv_path = write_csv("date,description,amount,currency\n2026-10-03,Taxi,12.50,USD\n2026-10-05,Lunch,9,EUR\n")
        paths = [csv_path, write_file("d.json", json_text()), write_file("d.xml", xml_text()), write_xlsx()]
        self.assertEqual(len({summary(read_expenses(p)) for p in paths}), 1)

    def test_cli_json(self) -> None:
        path = write_file("d.json", json_text())
        out = subprocess.run([sys.executable, "-m", "report", str(path)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("2 expenses from", out.stdout)

    def test_cli_unsupported_exits_1(self) -> None:
        path = write_file("d.txt", "x")
        out = subprocess.run([sys.executable, "-m", "report", str(path)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)


if __name__ == "__main__":
    unittest.main()

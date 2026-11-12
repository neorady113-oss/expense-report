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
EXPECTED = "2026-09\n  EUR 9\n  USD 30.00\n\n2026-10\n  USD 12.50\n"


class CliByMonth(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_flag_before_path(self) -> None:
        out = self.run_cli("--by-month", str(write_csv(CSV_TEXT)))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.replace("\r\n", "\n"), EXPECTED)

    def test_flag_after_path(self) -> None:
        out = self.run_cli(str(write_csv(CSV_TEXT)), "--by-month")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.replace("\r\n", "\n"), EXPECTED)

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


if __name__ == "__main__":
    unittest.main()

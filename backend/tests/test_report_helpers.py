import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.report_repository import ReportRepository


class PctHelperTest(unittest.TestCase):
    def test_zero_denominator_returns_zero(self) -> None:
        self.assertEqual(ReportRepository._pct(0, 0), 0.0)

    def test_zero_numerator_returns_zero(self) -> None:
        self.assertEqual(ReportRepository._pct(0, 100), 0.0)

    def test_full_conversion(self) -> None:
        self.assertEqual(ReportRepository._pct(100, 100), 100.0)

    def test_half_conversion(self) -> None:
        self.assertEqual(ReportRepository._pct(50, 100), 50.0)

    def test_rounds_to_two_decimals(self) -> None:
        self.assertEqual(ReportRepository._pct(1, 3), 33.33)

    def test_typical_funnel_conversion(self) -> None:
        # 247 contracted из 1000 entered = 24.7%
        self.assertEqual(ReportRepository._pct(247, 1000), 24.7)


class CoerceDateHelperTest(unittest.TestCase):
    def test_none_returns_none(self) -> None:
        self.assertIsNone(ReportRepository._coerce_date(None))

    def test_string_iso_parsed(self) -> None:
        self.assertEqual(ReportRepository._coerce_date("2026-04-25"), date(2026, 4, 25))

    def test_date_object_returned_as_is(self) -> None:
        d = date(2026, 1, 1)
        self.assertIs(ReportRepository._coerce_date(d), d)

    def test_invalid_string_raises(self) -> None:
        with self.assertRaises(ValueError):
            ReportRepository._coerce_date("not-a-date")


class StrictStageConditionsKeysTest(unittest.TestCase):
    """Проверяет, что _strict_stage_conditions возвращает все нужные ключи воронки."""

    def setUp(self) -> None:
        from app.api.report_filters import ReportFilters
        self.repo = ReportRepository()
        self.filters = ReportFilters(
            start_date=None, end_date=None,
            bots=[], advertising_companies=[],
            utm_source=[], utm_campaign=[],
            utm_medium=[], utm_content=[], utm_term=[],
        )

    def test_all_funnel_keys_present(self) -> None:
        expected = {"lead", "platform", "learning", "course", "simulator",
                    "interview", "passed", "offer", "contract", "distance_grinding"}
        conditions = self.repo._strict_stage_conditions(self.filters)
        self.assertEqual(set(conditions.keys()), expected)

    def test_conditions_are_not_none(self) -> None:
        conditions = self.repo._strict_stage_conditions(self.filters)
        for key, cond in conditions.items():
            self.assertIsNotNone(cond, f"condition for '{key}' is None")

    def test_stage_count(self) -> None:
        conditions = self.repo._strict_stage_conditions(self.filters)
        self.assertEqual(len(conditions), 10)


if __name__ == "__main__":
    unittest.main()

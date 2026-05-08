import unittest

from app.api.routers.reports_funnel_parts.reports_funnel_raw import _normalize_touch_mode


class TouchModeContractTest(unittest.TestCase):
    def test_normalize_touch_mode_accepts_primary_enum(self) -> None:
        self.assertEqual(_normalize_touch_mode("event"), "event")
        self.assertEqual(_normalize_touch_mode("first_touch"), "first")
        self.assertEqual(_normalize_touch_mode("last_touch"), "last")

    def test_normalize_touch_mode_accepts_legacy_aliases(self) -> None:
        self.assertEqual(_normalize_touch_mode("first"), "first")
        self.assertEqual(_normalize_touch_mode("last"), "last")

    def test_normalize_touch_mode_fallbacks_to_event(self) -> None:
        self.assertEqual(_normalize_touch_mode("unknown"), "event")
        self.assertEqual(_normalize_touch_mode(""), "event")


if __name__ == "__main__":
    unittest.main()

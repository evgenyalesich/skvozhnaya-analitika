import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.utm_normalization import (
    normalize_utm_key,
    normalize_utm_value,
    normalize_utm_filter_values,
)


class NormalizeUtmValueTest(unittest.TestCase):
    def test_none_returns_none(self) -> None:
        self.assertIsNone(normalize_utm_value(None))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(normalize_utm_value(""))
        self.assertIsNone(normalize_utm_value("   "))

    def test_placeholder_none_returns_none(self) -> None:
        self.assertIsNone(normalize_utm_value("none"))
        self.assertIsNone(normalize_utm_value("(none)"))
        self.assertIsNone(normalize_utm_value("NONE"))

    def test_placeholder_dash_returns_none(self) -> None:
        self.assertIsNone(normalize_utm_value("-"))
        self.assertIsNone(normalize_utm_value("—"))

    def test_placeholder_null_returns_none(self) -> None:
        self.assertIsNone(normalize_utm_value("null"))
        self.assertIsNone(normalize_utm_value("нет метки"))

    def test_real_value_returned(self) -> None:
        self.assertEqual(normalize_utm_value("facebook"), "facebook")
        self.assertEqual(normalize_utm_value("  vk  "), "vk")

    def test_url_encoded_value_decoded(self) -> None:
        self.assertEqual(normalize_utm_value("spring%20sale"), "spring sale")

    def test_url_encoded_placeholder_returns_none(self) -> None:
        self.assertIsNone(normalize_utm_value("%28none%29"))


class NormalizeUtmFilterValuesTest(unittest.TestCase):
    def test_empty_list_returns_empty(self) -> None:
        self.assertEqual(normalize_utm_filter_values([]), [])

    def test_none_returns_empty(self) -> None:
        self.assertEqual(normalize_utm_filter_values(None), [])

    def test_placeholders_filtered_out(self) -> None:
        self.assertEqual(normalize_utm_filter_values(["(none)", "-", "null"]), [])

    def test_deduplication(self) -> None:
        result = normalize_utm_filter_values(["Facebook", "facebook", "FACEBOOK"])
        self.assertEqual(result, ["facebook"])

    def test_lowercased(self) -> None:
        result = normalize_utm_filter_values(["VK"])
        self.assertEqual(result, ["vk"])

    def test_sorted_output(self) -> None:
        result = normalize_utm_filter_values(["vk", "facebook", "google"])
        self.assertEqual(result, ["facebook", "google", "vk"])

    def test_mixed_valid_and_placeholder(self) -> None:
        result = normalize_utm_filter_values(["facebook", "(none)", "vk", ""])
        self.assertEqual(result, ["facebook", "vk"])


class NormalizeUtmKeyTest(unittest.TestCase):
    def test_standard_keys_mapped(self) -> None:
        self.assertEqual(normalize_utm_key("utm_source"), "utm_source")
        self.assertEqual(normalize_utm_key("utm_campaign"), "utm_campaign")
        self.assertEqual(normalize_utm_key("utm_medium"), "utm_medium")
        self.assertEqual(normalize_utm_key("utm_content"), "utm_content")
        self.assertEqual(normalize_utm_key("utm_term"), "utm_term")

    def test_short_aliases_mapped(self) -> None:
        self.assertEqual(normalize_utm_key("source"), "utm_source")
        self.assertEqual(normalize_utm_key("campaign"), "utm_campaign")
        self.assertEqual(normalize_utm_key("medium"), "utm_medium")
        self.assertEqual(normalize_utm_key("content"), "utm_content")
        self.assertEqual(normalize_utm_key("term"), "utm_term")

    def test_unknown_key_returns_none(self) -> None:
        self.assertIsNone(normalize_utm_key("unknown_field"))
        self.assertIsNone(normalize_utm_key(""))

    def test_non_string_returns_none(self) -> None:
        self.assertIsNone(normalize_utm_key(None))
        self.assertIsNone(normalize_utm_key(123))

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_utm_key("UTM_SOURCE"), "utm_source")
        self.assertEqual(normalize_utm_key("Source"), "utm_source")


if __name__ == "__main__":
    unittest.main()

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ingestion.pokerhub_ingestor import PokerHubIngestor


class PokerHubIngestorMirrorTest(unittest.TestCase):
    def test_extracts_learn_start_from_json_string_lessons(self) -> None:
        ingestor = PokerHubIngestor()
        lessons = (
            '["Базовый курс: Урок 1. Правила игры '
            '(2026-04-12T15:51:37.000000Z)"]'
        )

        self.assertEqual(
            ingestor._extract_earliest_lesson_ts(lessons).isoformat(),
            "2026-04-12T15:51:37",
        )

    def test_detects_course_from_json_string_courses(self) -> None:
        ingestor = PokerHubIngestor()

        self.assertEqual(ingestor._detect_course('["Базовый курс", "SPIN1"]'), "SPIN")

    def test_detects_base_course_when_no_direction_course_exists(self) -> None:
        ingestor = PokerHubIngestor()

        self.assertEqual(ingestor._detect_course('["Базовый курс"]'), "BASE")

    def test_extracts_utm_from_direct_link_params(self) -> None:
        ingestor = PokerHubIngestor()
        payload = {
            "raw_link": "https://example.com/?source=direct&campaign=spring&medium=link&content=c1&term=t1"
        }
        utm = ingestor._extract_utm_from_payload(payload)

        self.assertEqual(utm.get("utm_source"), "direct")
        self.assertEqual(utm.get("utm_campaign"), "spring")
        self.assertEqual(utm.get("utm_medium"), "link")
        self.assertEqual(utm.get("utm_content"), "c1")
        self.assertEqual(utm.get("utm_term"), "t1")


if __name__ == "__main__":
    unittest.main()

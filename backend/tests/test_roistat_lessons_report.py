import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.report_filters import ReportFilters
from app.services.roistat_lessons_report import RoistatLessonsReport


class RoistatLessonsReportTest(unittest.IsolatedAsyncioTestCase):
    async def test_build_includes_direct_source_user_without_tg_id(self) -> None:
        report = RoistatLessonsReport()
        report._load_cohort_ph_ids = AsyncMock(return_value=None)  # type: ignore[method-assign]
        report._load_users = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "tg_user_id": None,
                    "username": "direct_user",
                    "ph_user_id": "4202",
                    "summary": {
                        "pokerhub_user_id": "4202",
                        "username": "direct_user",
                        "courses": {
                            "BASE": [
                                {
                                    "key": "l1",
                                    "label": "Урок 1",
                                    "module": None,
                                    "lesson": 1,
                                    "date": "2026-04-08",
                                }
                            ]
                        },
                    },
                }
            ]
        )

        courses = await report.build(
            session=None,  # type: ignore[arg-type]
            filters=ReportFilters(
                start_date=None,
                end_date=None,
                bots=[],
                advertising_companies=[],
                utm_source=[],
                utm_campaign=[],
                utm_medium=[],
                utm_content=[],
                utm_term=[],
                user_scope=None,
            ),
        )

        base = next(course for course in courses if course.course == "BASE")
        self.assertEqual(len(base.rows), 1)
        self.assertIsNone(base.rows[0].tg_user_id)
        self.assertEqual(base.rows[0].pokerhub_user_id, "4202")


if __name__ == "__main__":
    unittest.main()

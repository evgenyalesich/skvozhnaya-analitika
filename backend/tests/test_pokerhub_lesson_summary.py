import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.pokerhub_lesson_summary import PokerHubLessonSummaryBuilder


class PokerHubLessonSummaryBuilderMirrorTest(unittest.TestCase):
    def test_build_supports_mirror_payload_fields(self) -> None:
        builder = PokerHubLessonSummaryBuilder()
        payload = {
            "ph_id": "3571",
            "username": "mirror_user",
            "group": "tg-cash",
            "groups": '["tg-cash"]',
            "courses": {
                "CASH": [
                    ["Кэш. Модуль 1. Урок 1", "2026-04-17T17:16:08Z"],
                ]
            },
        }

        summary = builder.build(payload, course_catalog={})

        self.assertEqual(summary["pokerhub_user_id"], "3571")
        self.assertEqual(summary["username"], "mirror_user")
        self.assertEqual(len(summary["courses"]["CASH"]), 1)
        self.assertEqual(summary["courses"]["CASH"][0]["key"], "m1_l1")
        self.assertEqual(summary["courses"]["CASH"][0]["date"], "2026-04-17")

    def test_build_supports_flat_mirror_lessons_payload(self) -> None:
        builder = PokerHubLessonSummaryBuilder()
        payload = {
            "ph_id": "4202",
            "username": "direct_user",
            "courses": ["Базовый курс"],
            "lessons": [
                "Базовый курс: Урок 1. Правила игры в техасский холдем (2026-04-14T06:17:45.000000Z)",
                "Базовый курс: Урок 2. Комбинации в покере (2026-04-14T06:21:21.000000Z)",
            ],
            "course_memberships": ["base"],
        }

        summary = builder.build(payload, course_catalog={})

        self.assertEqual(summary["pokerhub_user_id"], "4202")
        self.assertEqual(len(summary["courses"]["BASE"]), 2)
        self.assertEqual(summary["courses"]["BASE"][0]["key"], "l1")
        self.assertEqual(summary["courses"]["BASE"][0]["date"], "2026-04-14")

    def test_build_routes_post_base_groups_to_new_courses(self) -> None:
        builder = PokerHubLessonSummaryBuilder()
        payload = {
            "ph_id": "4218",
            "groups": ["Базовый курс", "MTT after base couse"],
            "courses": ["Базовый курс", "MTT1"],
            "lessons": [
                "MTT1: MTT Модуль 1 Урок 1. Путь MTT игрока. Видео-презентация. (2026-04-09T12:46:16.000000Z)",
                "MTT1: MTT Модуль 1 Урок 2. Как играть турниры. Часть 1 (2026-04-09T12:46:28.000000Z)",
            ],
        }

        summary = builder.build(payload, course_catalog={})

        self.assertEqual(len(summary["courses"]["MTT_NEW"]), 2)
        self.assertEqual(len(summary["courses"]["MTT"]), 0)


if __name__ == "__main__":
    unittest.main()

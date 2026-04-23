import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.ingestion_service import BotIngestionService


class LeadIngestionConfigTest(unittest.TestCase):
    def test_build_lead_identity_select_with_telegram_mapping_keeps_tg_and_direct_users(self) -> None:
        tg_expr, ph_expr, where_clause = BotIngestionService._build_lead_identity_select(
            {"id", "telegram_id", "username"},
            has_lead_resources=True,
        )

        self.assertEqual(tg_expr, "COALESCE(users.telegram_id, -users.id)")
        self.assertIn("users.telegram_id IS NULL", ph_expr)
        self.assertIn("users.id BETWEEN 1 AND 2147483647", ph_expr)
        self.assertTrue(ph_expr.endswith("AS ph_user_id"))
        self.assertEqual(where_clause, "")

    def test_build_lead_identity_select_without_telegram_mapping_uses_positive_local_ids(self) -> None:
        tg_expr, ph_expr, where_clause = BotIngestionService._build_lead_identity_select(
            {"id", "username"},
            has_lead_resources=True,
        )

        self.assertEqual(tg_expr, "users.id")
        self.assertEqual(ph_expr, "NULL::integer AS ph_user_id")
        self.assertEqual(where_clause, "")

    def test_build_lead_identity_select_without_lead_resources_still_uses_positive_local_ids(self) -> None:
        tg_expr, ph_expr, where_clause = BotIngestionService._build_lead_identity_select(
            {"id", "username"},
            has_lead_resources=False,
        )

        self.assertEqual(tg_expr, "users.id")
        self.assertEqual(ph_expr, "NULL::integer AS ph_user_id")
        self.assertEqual(where_clause, "")


if __name__ == "__main__":
    unittest.main()

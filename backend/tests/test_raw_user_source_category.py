import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.analytics import RawBotUser
from app.services.raw_user_repository import RawUserRepository


class RawUserSourceCategoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = RawUserRepository()

    def test_lead_user_with_same_ph_and_tg_identity_is_direct_source(self) -> None:
        user = RawBotUser(bot_key="lead", tg_user_id=4280, ph_user_id=4280)

        self.assertEqual(self.repo._derive_source_category(user), "direct_source")

    def test_lead_user_with_distinct_ph_identity_is_almanah(self) -> None:
        user = RawBotUser(bot_key="lead", tg_user_id=8646356072, ph_user_id=4396)

        self.assertEqual(self.repo._derive_source_category(user), "almanah")

    def test_lead_user_with_only_tg_identity_is_almanah(self) -> None:
        user = RawBotUser(bot_key="lead", tg_user_id=6163468982, ph_user_id=None)

        self.assertEqual(self.repo._derive_source_category(user), "almanah")


if __name__ == "__main__":
    unittest.main()

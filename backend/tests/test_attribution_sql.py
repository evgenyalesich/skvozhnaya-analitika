import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ATTRIBUTION_SERVICE = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "attribution_service.py"
)


class AttributionSqlStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql_source = ATTRIBUTION_SERVICE.read_text(encoding="utf-8")

    # --- Boundaries ----------------------------------------------------------

    def test_last_touch_uses_platform_registered_at(self) -> None:
        self.assertIn("platform_registered_at", self.sql_source)

    def test_last_touch_does_not_use_learn_start_date(self) -> None:
        self.assertNotIn("learn_start_date", self.sql_source)

    # --- Deduplication -------------------------------------------------------

    def test_first_touch_uses_distinct_on(self) -> None:
        self.assertIn("DISTINCT ON (tg_user_id)", self.sql_source)

    def test_last_touch_uses_distinct_on(self) -> None:
        self.assertIn("DISTINCT ON (raw.tg_user_id)", self.sql_source)

    # --- Lead exclusion ------------------------------------------------------

    def test_lead_bots_excluded_from_first_touch(self) -> None:
        self.assertIn("NOT LIKE 'lead%'", self.sql_source)

    def test_excluded_bots_param_used(self) -> None:
        self.assertIn(":excluded_bots", self.sql_source)

    # --- Ordering ------------------------------------------------------------

    def test_first_touch_ordered_asc(self) -> None:
        self.assertIn("ORDER BY tg_user_id, created_at ASC", self.sql_source)

    def test_last_touch_ordered_desc(self) -> None:
        self.assertIn("ORDER BY raw.tg_user_id, raw.created_at DESC", self.sql_source)

    # --- Update strategy -----------------------------------------------------

    def test_single_update_with_full_join(self) -> None:
        self.assertIn("FULL JOIN", self.sql_source)

    def test_update_uses_coalesce_for_missing_touch(self) -> None:
        self.assertIn("COALESCE(ft.bot_key,", self.sql_source)
        self.assertIn("COALESCE(lt.bot_key,", self.sql_source)

    def test_update_is_idempotent_via_is_distinct_from(self) -> None:
        # Пропускает строки, у которых ничего не изменилось
        self.assertIn("IS DISTINCT FROM", self.sql_source)

    # --- Lock safety ---------------------------------------------------------

    def test_lock_timeout_set(self) -> None:
        self.assertIn("lock_timeout", self.sql_source)

    def test_retry_logic_present(self) -> None:
        self.assertIn("_execute_with_retry", self.sql_source)

    # --- Docstring accuracy --------------------------------------------------

    def test_docstring_mentions_platform_registered_at(self) -> None:
        self.assertIn("platform_registered_at", self.sql_source)

    def test_docstring_does_not_mention_learn_start_date(self) -> None:
        self.assertNotIn("learn_start_date", self.sql_source)


if __name__ == "__main__":
    unittest.main()

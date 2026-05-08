import unittest
from pathlib import Path


ROISTAT_WEEKLY_BOT_QUERY = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "api"
    / "routers"
    / "reports_roistat_companies_parts"
    / "reports_roistat_companies_runtime_query_bot_weekly.py"
)


class MainReportBotSqlRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weekly_bot_sql = ROISTAT_WEEKLY_BOT_QUERY.read_text(encoding="utf-8")

    def test_weekly_bot_platform_metrics_use_actual_bot_key(self) -> None:
        self.assertIn("start_rows AS (", self.weekly_bot_sql)
        self.assertIn("SELECT DISTINCT ON (r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'))", self.weekly_bot_sql)
        self.assertIn("COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key", self.weekly_bot_sql)

    def test_weekly_bot_learning_metrics_use_actual_bot_key(self) -> None:
        self.assertIn("bot_metrics AS (", self.weekly_bot_sql)
        self.assertIn("sr.bot_key,", self.weekly_bot_sql)
        platform_filter = "uf.ph_user_id IS NOT NULL AND uf.did_platform"
        self.assertIn(f"COUNT(DISTINCT CASE WHEN uf.did_lead AND {platform_filter} AND uf.did_learning THEN uf.ph_user_id END) AS started_learning", self.weekly_bot_sql)
        self.assertIn(f"COUNT(DISTINCT CASE WHEN uf.did_lead AND {platform_filter} AND uf.is_mtt THEN uf.ph_user_id END) AS mtt", self.weekly_bot_sql)
        self.assertIn(f"COUNT(DISTINCT CASE WHEN uf.did_lead AND {platform_filter} AND uf.is_spin THEN uf.ph_user_id END) AS spin", self.weekly_bot_sql)
        self.assertIn(f"COUNT(DISTINCT CASE WHEN uf.did_lead AND {platform_filter} AND uf.is_cash THEN uf.ph_user_id END) AS cash", self.weekly_bot_sql)
        self.assertNotIn("first_platform_date BETWEEN sr.week_start AND (sr.week_start + INTERVAL '6 day')::date", self.weekly_bot_sql)
        self.assertNotIn("uf.did_learning AND uf.is_mtt", self.weekly_bot_sql)
        self.assertNotIn("uf.did_learning AND uf.is_spin", self.weekly_bot_sql)
        self.assertNotIn("uf.did_learning AND uf.is_cash", self.weekly_bot_sql)

    def test_weekly_bot_platform_metrics_count_distinct_ph_user_id(self) -> None:
        self.assertIn("MIN((ru.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (", self.weekly_bot_sql)
        self.assertIn("MIN(ru.ph_user_id) FILTER (", self.weekly_bot_sql)
        self.assertIn("THEN uf.ph_user_id", self.weekly_bot_sql)

    def test_weekly_bot_metrics_are_built_from_start_cohort_and_user_flags(self) -> None:
        self.assertIn("user_flags AS (", self.weekly_bot_sql)
        self.assertIn("WHERE ru.tg_user_id IN (SELECT tg_user_id FROM attributed_leads)", self.weekly_bot_sql)
        self.assertIn("BOOL_OR(ru.converted_to_lead IS TRUE OR lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead", self.weekly_bot_sql)
        self.assertIn("FROM start_rows sr", self.weekly_bot_sql)


if __name__ == "__main__":
    unittest.main()

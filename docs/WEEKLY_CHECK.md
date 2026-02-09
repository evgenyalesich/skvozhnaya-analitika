# Weekly DoD SQL Check

Purpose: validate `Weekly` numbers for a fixed first-touch cohort period and one calendar month.

Rules checked:
- Cohort filter: users with first touch in [`:ft_start`, `:ft_end`]
- Metrics by event dates, not first_touch date:
  - `almanah_starts` by first lead% touch week
  - `platform` by `platform_registered_at` week
  - `learning` by `learn_start_date` week
  - `not_started` by platform week where `started_learning=false`
  - `saloon` by subscription event week

## Query

Replace parameters before running:
- `:ft_start` e.g. `2025-12-01`
- `:ft_end` e.g. `2025-12-24`
- `:month_start` e.g. `2025-12-01`
- `:month_end` e.g. `2025-12-31`
- `:community_id` your Telegram saloon channel id

```sql
WITH first_touch AS (
  SELECT
    tg_user_id,
    MIN(created_at)::date AS first_touch_date
  FROM raw_bot_users
  WHERE created_at IS NOT NULL
    AND bot_key IS NOT NULL
    AND trim(bot_key) <> ''
    AND lower(trim(bot_key)) NOT LIKE 'lead%'
  GROUP BY tg_user_id
),
cohort AS (
  SELECT tg_user_id
  FROM first_touch
  WHERE first_touch_date >= DATE ':ft_start'
    AND first_touch_date <= DATE ':ft_end'
),
user_flags AS (
  SELECT
    tg_user_id,
    BOOL_OR(registered_platform IS TRUE) AS registered_platform,
    BOOL_OR(started_learning IS TRUE) AS started_learning
  FROM raw_bot_users
  GROUP BY tg_user_id
),
almanah_touch AS (
  SELECT
    tg_user_id,
    MIN(created_at)::date AS event_date
  FROM raw_bot_users
  WHERE created_at IS NOT NULL
    AND lower(COALESCE(bot_key, '')) LIKE 'lead%'
  GROUP BY tg_user_id
),
platform_touch AS (
  SELECT
    tg_user_id,
    MIN(platform_registered_at)::date AS event_date
  FROM raw_bot_users
  WHERE registered_platform IS TRUE
    AND platform_registered_at IS NOT NULL
  GROUP BY tg_user_id
),
learning_touch AS (
  SELECT
    tg_user_id,
    MIN(learn_start_date)::date AS event_date
  FROM raw_bot_users
  WHERE learn_start_date IS NOT NULL
  GROUP BY tg_user_id
),
not_started_touch AS (
  SELECT
    p.tg_user_id,
    p.event_date
  FROM platform_touch p
  JOIN user_flags uf ON uf.tg_user_id = p.tg_user_id
  WHERE COALESCE(uf.started_learning, FALSE) IS FALSE
),
saloon_touch AS (
  SELECT
    e.tg_user_id,
    e.checked_at::date AS event_date
  FROM telegram_subscription_events e
  WHERE e.status = 'subscribed'
    AND e.channel_id = ':community_id'
),
weekly AS (
  SELECT DATE_TRUNC('week', event_date)::date AS week_start, COUNT(*) AS almanah_starts, 0::bigint AS platform, 0::bigint AS learning, 0::bigint AS not_started, 0::bigint AS saloon
  FROM almanah_touch a JOIN cohort c USING (tg_user_id)
  GROUP BY 1
  UNION ALL
  SELECT DATE_TRUNC('week', event_date)::date, 0, COUNT(*), 0, 0, 0
  FROM platform_touch p JOIN cohort c USING (tg_user_id)
  GROUP BY 1
  UNION ALL
  SELECT DATE_TRUNC('week', event_date)::date, 0, 0, COUNT(*), 0, 0
  FROM learning_touch l JOIN cohort c USING (tg_user_id)
  GROUP BY 1
  UNION ALL
  SELECT DATE_TRUNC('week', event_date)::date, 0, 0, 0, COUNT(*), 0
  FROM not_started_touch n JOIN cohort c USING (tg_user_id)
  GROUP BY 1
  UNION ALL
  SELECT DATE_TRUNC('week', event_date)::date, 0, 0, 0, 0, COUNT(DISTINCT s.tg_user_id)
  FROM saloon_touch s JOIN cohort c USING (tg_user_id)
  GROUP BY 1
)
SELECT
  week_start,
  SUM(almanah_starts)::int AS almanah_starts,
  SUM(platform)::int AS platform,
  SUM(learning)::int AS learning,
  SUM(not_started)::int AS not_started,
  SUM(saloon)::int AS saloon
FROM weekly
WHERE week_start >= DATE ':month_start'
  AND week_start <= DATE ':month_end'
GROUP BY week_start
ORDER BY week_start;
```

## Acceptance
- Compare this SQL result with UI `Weekly` week rows for the same month.
- Required mismatch: exactly `0` for all 5 metrics.

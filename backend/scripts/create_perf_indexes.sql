CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_created_tg
ON raw_bot_users (created_at, tg_user_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_bot_created
ON raw_bot_users (bot_key, created_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_company_created
ON raw_bot_users (advertising_company, created_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_tg_created
ON raw_bot_users (tg_user_id, created_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_learn_start_tg
ON raw_bot_users (learn_start_date, tg_user_id)
WHERE learn_start_date IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_first_touch_tg
ON raw_bot_users (first_touch_bot, tg_user_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_last_touch_tg
ON raw_bot_users (last_touch_bot, tg_user_id);

CREATE TABLE IF NOT EXISTS agg_weekly_funnel_bot (
    id SERIAL PRIMARY KEY,
    week_start DATE NOT NULL,
    bot_key VARCHAR(64) NOT NULL,
    entered INTEGER NOT NULL DEFAULT 0,
    new_in_system INTEGER NOT NULL DEFAULT 0,
    old_in_system INTEGER NOT NULL DEFAULT 0,
    lead INTEGER NOT NULL DEFAULT 0,
    subscribed INTEGER NOT NULL DEFAULT 0,
    platform INTEGER NOT NULL DEFAULT 0,
    learning INTEGER NOT NULL DEFAULT 0,
    course INTEGER NOT NULL DEFAULT 0,
    simulator INTEGER NOT NULL DEFAULT 0,
    interview INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    offer INTEGER NOT NULL DEFAULT 0,
    contract INTEGER NOT NULL DEFAULT 0,
    distance_grinding INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_weekly_funnel_bot UNIQUE (week_start, bot_key)
);

CREATE INDEX IF NOT EXISTS idx_weekly_funnel_bot_lookup
ON agg_weekly_funnel_bot (bot_key, week_start);

CREATE TABLE IF NOT EXISTS agg_weekly_funnel_company (
    id SERIAL PRIMARY KEY,
    week_start DATE NOT NULL,
    advertising_company VARCHAR(128) NOT NULL,
    entered INTEGER NOT NULL DEFAULT 0,
    new_in_system INTEGER NOT NULL DEFAULT 0,
    old_in_system INTEGER NOT NULL DEFAULT 0,
    lead INTEGER NOT NULL DEFAULT 0,
    subscribed INTEGER NOT NULL DEFAULT 0,
    platform INTEGER NOT NULL DEFAULT 0,
    learning INTEGER NOT NULL DEFAULT 0,
    course INTEGER NOT NULL DEFAULT 0,
    simulator INTEGER NOT NULL DEFAULT 0,
    interview INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    offer INTEGER NOT NULL DEFAULT 0,
    contract INTEGER NOT NULL DEFAULT 0,
    distance_grinding INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_weekly_funnel_company UNIQUE (week_start, advertising_company)
);

CREATE INDEX IF NOT EXISTS idx_weekly_funnel_company_lookup
ON agg_weekly_funnel_company (advertising_company, week_start);

CREATE TABLE IF NOT EXISTS moderation_cases (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    case_id INTEGER NOT NULL,
    moderator_id BIGINT NOT NULL,
    target_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, case_id)
);

CREATE TABLE IF NOT EXISTS birthdays (
    user_id BIGINT PRIMARY KEY,
    birthday TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS birthday_config (
    guild_id BIGINT PRIMARY KEY,
    role_id BIGINT,
    channel_id BIGINT,
    message TEXT DEFAULT 'Happy birthday {user}, enjoy your role today 🎉🎂',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS highlights (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    keyword TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id, keyword)
);

CREATE INDEX IF NOT EXISTS idx_moderation_cases_guild ON moderation_cases(guild_id);
CREATE INDEX IF NOT EXISTS idx_moderation_cases_target ON moderation_cases(target_id);
CREATE INDEX IF NOT EXISTS idx_birthdays_date ON birthdays(EXTRACT(MONTH FROM birthday), EXTRACT(DAY FROM birthday));
CREATE INDEX IF NOT EXISTS idx_highlights_guild ON highlights(guild_id);
CREATE INDEX IF NOT EXISTS idx_highlights_user ON highlights(user_id);

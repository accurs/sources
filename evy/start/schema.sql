CREATE TABLE IF NOT EXISTS snipe (
    message_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    author_id BIGINT NOT NULL,
    content TEXT NOT NULL
    
);
CREATE TABLE IF NOT EXISTS economy (
    user_id   BIGINT,
    guild_id  BIGINT,
    wallet    BIGINT DEFAULT 0,
    bank      BIGINT DEFAULT 0,
    bank_max  BIGINT DEFAULT 5000,
    inventory JSONB  DEFAULT '{}',
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS economy_cooldowns (
    user_id  BIGINT,
    guild_id BIGINT,
    key      TEXT,
    expires  DOUBLE PRECISION,
    PRIMARY KEY (user_id, guild_id, key)
);
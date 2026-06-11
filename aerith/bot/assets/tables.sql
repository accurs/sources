CREATE EXTENSION IF NOT EXISTS citext;

CREATE SCHEMA IF NOT EXISTS api;

CREATE TABLE IF NOT EXISTS api.commands (
    id SERIAL PRIMARY KEY,
    extension TEXT NOT NULL,
    command TEXT NOT NULL,
    aliases TEXT[],
    permissions TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api.status (
    shard_id TEXT PRIMARY KEY,
    latency TEXT,
    guilds TEXT,
    users TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    prefix VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS guilds (
    id BIGINT PRIMARY KEY,
    prefix VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS welcomes (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT,
    self_destruct INTEGER,
    message TEXT
);

CREATE TABLE IF NOT EXISTS lefts (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT,
    self_destruct INTEGER,
    message TEXT
);

CREATE TABLE IF NOT EXISTS boosts (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT,
    self_destruct INTEGER,
    message TEXT
);

CREATE TABLE IF NOT EXISTS lastfm (
    discord_id TEXT PRIMARY KEY,
    lastfm_username TEXT NOT NULL,
    session_key TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    command TEXT DEFAULT 'fm',
    message TEXT,
    sessionused BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS embed (
    name TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    color TEXT,
    thumbnail TEXT,
    image TEXT,
    author_name TEXT,
    author_icon TEXT,
    footer_text TEXT,
    footer_icon TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW(),    
    fields JSONB
)
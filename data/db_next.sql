CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    avatar_url TEXT NOT NULL,
    triggers TEXT NOT NULL,
    owner INTEGER NOT NULL,
    times_used INTEGER,
    creation_date REAL,
    nickname TEXT NOT NULL,
    proxy_forms TEXT NOT NULL, -- {str: url}
    current_form TEXT NOT NULL,
    pronouns TEXT NOT NULL,
    FOREIGN KEY (owner) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS proxy_tags_map (
    proxy_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (proxy_id, tag_id),
    FOREIGN KEY (proxy_id) REFERENCES proxies (id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES proxy_tags (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS proxy_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    owner INTEGER NOT NULL,
    creation_date REAL,
    tag TEXT NOT NULL,
    FOREIGN KEY (owner) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS channel_webhook_map (
    channel_id INTEGER,
    webhook_id INTEGER,
    guild_type INTEGER,
    PRIMARY KEY (channel_id, guild_type)
);

CREATE TABLE IF NOT EXISTS global_stats (
    key TEXT PRIMARY KEY,
    value REAL
);
INSERT OR IGNORE INTO global_stats (key, value) VALUES ('version', 21);

CREATE TABLE IF NOT EXISTS permission_overrides (
    guild_id INTEGER,
    guild_type INTEGER,
    id INTEGER,
    id_type INTEGER,
    allows INTEGER,
    denies INTEGER,
    PRIMARY KEY (id, id_type, guild_id, guild_type)
); -- id_type: 0 - channel; 1 - role; 2 - user; 3 - base

CREATE TABLE IF NOT EXISTS guild_preferences (
    guild_id INTEGER,
    logging_channel INTEGER,
    dice_functions BLOB,
    guild_type INTEGER,
    PRIMARY KEY (guild_id, guild_type)
);

CREATE TABLE IF NOT EXISTS message_links (
    message_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    proxy_id INTEGER,
    platform_user INTEGER,
    platform_type INTEGER,
    FOREIGN KEY (proxy_id) REFERENCES proxies (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    private_description BOOLEAN,
    private_trigger BOOLEAN,
    private_metadata BOOLEAN,
    private_proxy_tags BOOLEAN,
    private_list BOOLEAN,
    private_forms BOOLEAN,
    private_spotlight BOOLEAN,
    private_pronouns BOOLEAN,
    spotlight TEXT, -- JSON [proxy id]
    dice_functions BLOB,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT
);

CREATE TABLE IF NOT EXISTS accounts (
    user_id INTEGER,
    account_type INTEGER,
    owner INTEGER NOT NULL,
    PRIMARY KEY (user_id, account_type),
    FOREIGN KEY (owner) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS autoproxies (
    guild_id INTEGER,
    user_id INTEGER,
    proxy INTEGER,
    last_used_proxy INTEGER,
    expires REAL,
    guild_type INTEGER,
    flags INTEGER,
    PRIMARY KEY (guild_id, user_id, guild_type),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_proxies_owner ON proxies (owner);
CREATE INDEX IF NOT EXISTS idx_message_links_channel ON message_links (channel_id);
CREATE INDEX IF NOT EXISTS idx_message_links_proxy ON message_links (proxy_id);
CREATE INDEX IF NOT EXISTS idx_autoproxies_guild_id ON autoproxies (guild_id);
CREATE INDEX IF NOT EXISTS idx_autoproxies_user_id ON autoproxies (user_id);
CREATE INDEX IF NOT EXISTS idx_accounts_query ON accounts (user_id, account_type);

PRAGMA foreign_key=ON;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-64000;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=268435456;
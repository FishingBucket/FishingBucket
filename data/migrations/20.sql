CREATE TABLE new_permission_overrides (
    guild_id INTEGER,
    guild_type INTEGER,
    id INTEGER,
    id_type INTEGER,
    allows INTEGER,
    denies INTEGER,
    PRIMARY KEY (id, id_type, guild_id, guild_type)
);

INSERT INTO new_permission_overrides (
    guild_id, guild_type, id, id_type, allows, denies
) SELECT
    guild_id, guild_type, id, id_type, IIF(allow_proxy = 1, 1, 0), IIF(allow_proxy = -1, 1, 0)
FROM permission_overrides;

DROP INDEX idx_permission_overrides_guild;
DROP INDEX idx_permission_overrides_id;

DROP TABLE permission_overrides;

ALTER TABLE new_permission_overrides RENAME TO permission_overrides;

UPDATE global_stats SET value = 20 WHERE key = 'version';
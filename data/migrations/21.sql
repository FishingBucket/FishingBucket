INSERT INTO permission_overrides (
    guild_id, guild_type, id, id_type, allows, denies
) SELECT
    guild_id, guild_type, 0, 3, IIF(disallow_by_default = TRUE, 1, 0), IIF(disallow_by_default != TRUE, 1, 0)
FROM guild_preferences;

ALTER TABLE guild_preferences DROP COLUMN disallow_by_default;

UPDATE global_stats SET value = 21 WHERE key = 'version';
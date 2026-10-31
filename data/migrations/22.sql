ALTER TABLE autoproxies ADD COLUMN last_used_timestamp REAL;
UPDATE autoproxies SET last_used_timestamp = unixepoch('subsec');

UPDATE global_stats SET value = 22 WHERE key = 'version';
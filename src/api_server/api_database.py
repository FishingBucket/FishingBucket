import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import NewType

import aiosqlite as sql
import json
import secrets

from ..backend.cache import TTLCache
from ..backend.database.user import UserID, SSOID
from ..backend.logging import start_log
from ..backend.models import Platform

print, error = start_log("database", "-api")

SessionID = NewType("SessionID", str)


@dataclass
class Session:
    session_id: SessionID
    user_id: UserID
    data: dict
    created: float
    expires: float
    platform: Platform
    sso_id: SSOID

class Cache:
    sessions: TTLCache[SessionID, Session] = TTLCache(4096, 3600)

SESSION_TTL = 3600 * 24

def this_time() -> float:
    return datetime.datetime.now().timestamp()


class Database:
    instance: Database

    def __init__(self, database_file: Path | str = "../api_database.db"):
        Database.instance = self
        self.connection: sql.Connection = None
        self.database_file = database_file

    async def init(self):
        self.connection = await sql.connect(self.database_file)
        await self.create_tables()
        await self.migrate()
        print("API database connection established.")

    async def create_tables(self):
        await self.connection.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            data TEXT,
            created REAL,
            expires REAL,
            platform_type INTEGER,
            sso_id INTEGER
        )
        """)
        await self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS meta (
            db_version INTEGER
        );
        INSERT INTO meta (db_version) SELECT 2 WHERE NOT EXISTS (SELECT 0 FROM meta);
        """)
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_session_ids ON sessions (id)")
        await self.connection.commit()

    async def migrate(self):
        try:
            async with self.connection.execute("SELECT db_version FROM meta LIMIT 1;") as cursor:
                version: int = (await cursor.fetchone())[0]
        except sql.DatabaseError as e:
            print(e)
            version = 0

        if version == 0:
            await self.connection.executescript("""
            ALTER TABLE sessions ADD COLUMN platform_type INTEGER;
            """)
            version += 1

        if version == 1:
            await self.connection.executescript("""
            ALTER TABLE sessions ADD COLUMN sso_id INTEGER;
            DELETE FROM sessions;
            """)
            version += 1

        async with self.connection.execute("UPDATE meta SET db_version = ?", (version, )): pass


    async def get_session(self, session_id: SessionID) -> Session | None:
        if ret := Cache.sessions.get(session_id):
            return ret

        async with self.connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id, )) as cursor:
            res = await cursor.fetchone()
            if not res: return None
            sess = Session(res[0], res[1], json.loads(res[2]), res[3], res[4], Platform.from_(res[5]), res[6])
            now = this_time()
            if now > sess.expires:
                await self.connection.execute("DELETE FROM sessions WHERE id = ?", (session_id, ))
                await self.connection.commit()
                Cache.sessions.invalidate(session_id)
                return None
            Cache.sessions.set(session_id, sess)
            return sess

    async def new_session(self, user_id: UserID, data: dict, platform: Platform, sso_id: SSOID) -> tuple[SessionID, float]:
        session_id = SessionID(secrets.token_hex(64))
        now = this_time()
        expires = now + SESSION_TTL
        await self.connection.execute(
            "INSERT INTO sessions (id, user_id, data, created, expires, platform_type, sso_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_id, json.dumps(data), now, expires, platform.get(), sso_id)
        )
        await self.connection.commit()
        return session_id, expires

    async def remove_all_sessions(self, user_id: UserID):
        async with self.connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id, )):
            Cache.sessions.clear(lambda k, v: v.user_id == user_id)

    async def remove_sessions_sso_id(self, sso_id: SSOID):
        async with self.connection.execute("DELETE FROM sessions WHERE sso_id = ?", (sso_id, )):
            Cache.sessions.clear(lambda k, v: v.sso_id == sso_id)

    async def update_user_id(self, session_id: SessionID, new_user_id: UserID) -> Session | None:
        async with self.connection.execute("UPDATE sessions SET user_id = ? WHERE id = ?", (new_user_id, session_id)):
            Cache.sessions.invalidate(session_id)
            return await self.get_session(session_id)

    async def extend_session(self, session_id: SessionID, new_time: float) -> Session | None:
        async with self.connection.execute("UPDATE sessions SET expires = ? WHERE id = ?", (new_time, session_id)) as cursor:
            Cache.sessions.invalidate(session_id)
            return await self.get_session(session_id)

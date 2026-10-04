__all__ = "get_db", "Database"

from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite as sql

from .guild import GuildRepository
from .permission import PermissionsRepository
from .proxy import ProxyRepository
from .relationship import RelationshipRepository
from .tag import ProxyTagRepository
from .user import UserRepository, UserID
from .user_setting import UserSettingRepository
from ..data_reader import DataReader
from ..logging import start_log

print, error = start_log("database")

db: Database

def get_db() -> Database:
    return db

class Database:
    def __init__(self, database_file: str | Path = "../database.db"):
        global db
        db = self
        self.connection: sql.Connection = None
        self.database_file = database_file
        self.users = UserRepository(self)
        self.proxies = ProxyRepository(self)
        self.tags = ProxyTagRepository(self)
        self.relationships = RelationshipRepository(self)
        self.guilds = GuildRepository(self)
        self.user_settings = UserSettingRepository(self)
        self.permissions = PermissionsRepository(self)

    async def init(self) -> None:
        self.connection = await sql.connect(self.database_file)
        self.connection.row_factory = sql.Row
        await self.create_tables()
        await self.migrate()
        await self.connection.execute("VACUUM")
        await self.connection.commit()
        print("Database connection established")

    async def create_tables(self):
        await self.connection.executescript(DataReader.instance["db_next.sql"])
        await self.connection.execute("PRAGMA journal_mode=WAL;")
        await self.connection.execute("PRAGMA synchronous=NORMAL;")
        await self.connection.execute("PRAGMA cache_size=-64000;") # 64MB cache
        await self.connection.execute("PRAGMA temp_store=MEMORY;")
        await self.connection.execute("PRAGMA mmap_size=268435456;") # 256MB mmap io
        await self.connection.commit()

    async def close(self):
        print("Closing database connection.")
        await self.connection.close()


    async def migrate(self):
        version = int((await self.get_global_stats()).get("version", 0))
        migrations_data = DataReader.instance["migrations/stats.json"]
        while str(version) in migrations_data:
            data_file = migrations_data[str(version)]
            if data_file == "unsupported":
                error(ValueError(f"Migrating from version {version} is now unsupported."))
                return
            migration_script = DataReader.instance[data_file]
            try:
                print(f"Migrating to version {version + 1}")
                await self.connection.executescript("BEGIN TRANSACTION;" + migration_script + "; COMMIT;")
            except Exception as e:
                await self.connection.execute("ROLLBACK;")
                error(e)
                return
            version += 1

        print(f"Finished migrating to version {int((await self.get_global_stats()).get("version", 0))}")

    async def set_global_data(self, key: str, value_exists: str, value_not_exists: float):
        await self.connection.execute(
            f"INSERT INTO global_stats (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = {value_exists} WHERE key = ?",
            (key, value_not_exists, key)
        ) # who the fuck cares about sql injection attacks? not me!
        await self.connection.commit()

    async def get_global_stats(self) -> dict[str, float]:
        cursor = await self.connection.execute("SELECT * FROM global_stats")
        d = {}
        for k, v in await cursor.fetchall():
            d[k] = v
        await cursor.close()
        return d


    async def nuke(self, user: UserID) -> None:
        await self.relationships.nuke(user)
        await self.proxies.nuke(user)
        await self.tags.nuke(user)


    async def delete_account(self, user: UserID) -> None:
        await self.connection.execute(
            """
            DELETE FROM message_links WHERE proxy_id IN (
                SELECT id FROM proxies WHERE owner = ?
            )
            """,
            (user,)
        )
        await self.user_settings.delete_account(user)
        await self.nuke(user)
        await self.users.delete_account(user)


    @asynccontextmanager
    async def transaction(self):
        try:
            yield
        except:
            await self.connection.rollback()
            raise
        finally:
            await self.connection.commit()

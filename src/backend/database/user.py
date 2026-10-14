from typing import TYPE_CHECKING, NewType

from ..cache import TTLCache
from ..models import Platform

if TYPE_CHECKING:
    from .database import Database

__all__ = "UserRepository", "UserID", "SSOID"

UserID = NewType("UserID", int)
SSOID = NewType("SSOID", int)


class Cache:
    users_from_sso = TTLCache[tuple[SSOID, Platform], UserID](2048, 3600)


class UserRepository:
    def __init__(self, database: Database) -> None:
        self.database = database


    async def get_user_id(self, sso: SSOID, platform: Platform) -> UserID | None:
        if cached := Cache.users_from_sso.get((sso, platform)):
            return cached

        async with self.database.connection.execute(
            "SELECT owner FROM accounts WHERE user_id = ? AND account_type = ?",
                (sso, platform.get())
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        owner = UserID(row["owner"])
        Cache.users_from_sso.set((sso, platform), owner)
        return owner


    async def get_or_create_user_id(self, sso: SSOID, platform: Platform) -> UserID:
        if user_id := await self.get_user_id(sso, platform):
            return user_id

        async with self.database.connection.execute(
            "INSERT INTO users DEFAULT VALUES RETURNING user_id"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            owner = UserID(row["user_id"])

        await self.link_accounts(owner, sso, platform)
        Cache.users_from_sso.set((sso, platform), owner)
        return owner


    async def link_accounts(self, user_id: UserID, sso_id: SSOID, platform: Platform) -> None:
        await self.database.connection.execute(
            "INSERT INTO accounts (user_id, account_type, owner) VALUES (?, ?, ?)",
            (sso_id, platform.get(), user_id)
        )


    async def unlink_account(self, sso_id: SSOID, platform: Platform) -> None:
        async with self.database.connection.execute(
            "DELETE FROM accounts WHERE user_id = ? AND account_type = ?",
                (sso_id, platform.get())
        ):
            Cache.users_from_sso.invalidate((sso_id, platform))


    async def get_accounts(self, user_id: UserID) -> list[tuple[SSOID, Platform]]:
        async with self.database.connection.execute(
            "SELECT user_id, account_type FROM accounts WHERE owner = ?",
                (user_id,)
        ) as cursor:
            return [
                (row["user_id"], Platform.from_(row["account_type"]))
                for row in await cursor.fetchall()
            ]


    async def delete_account(self, user_id: UserID) -> None:
        async with self.database.connection.execute(
            """
            DELETE FROM accounts WHERE owner = ?
            RETURNING user_id, account_type
            """,
                (user_id,)
        ) as cursor:
            for row in await cursor.fetchall():
                Cache.users_from_sso.invalidate((
                    SSOID(row["user_id"]),
                    Platform.from_(row["account_type"])
                ))
        await self.database.connection.execute(
            """
            DELETE FROM users WHERE user_id = ?
            """,
            (user_id,)
        )

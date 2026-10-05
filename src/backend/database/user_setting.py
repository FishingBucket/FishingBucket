import json
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Sequence

from sqlite3 import Row

from .user import UserID
from ..cache import TTLCache
from ..models import GuildDat, ID, Platform

if TYPE_CHECKING:
    from .database import Database


__all__ = "UserPreference", "AutoproxyPreference", "AutoproxyType", "UserSettingRepository"


class AutoproxyType(IntEnum):
    NORMAL = 0
    SPOTLIGHT = 1


@dataclass(slots=True, frozen=True)
class AutoproxyPreference:
    matched_guild: GuildDat
    set_proxy: ID | None
    last_used_proxy: ID | None
    expires: float | None
    type: AutoproxyType

    def do_expire_now(self) -> bool:
        return bool(self.expires and self.expires < time.time())

    @classmethod
    def from_database(cls, row: Row) -> AutoproxyPreference:
        return cls(
            GuildDat(
                row["guild_id"],
                Platform.from_(row["guild_type"])
            ),
            ID(row["proxy"]) if row["proxy"] is not None else None,
            ID(row["last_used_proxy"]) if row["last_used_proxy"] is not None else None,
            row["expires"],
            AutoproxyType(row["flags"] or 0)
        )

    def to_database(self) -> dict:
        return {
            "guild_id": self.matched_guild.guild_id,
            "guild_type": self.matched_guild.platform.get(),
            "proxy": self.set_proxy,
            "last_used_proxy": self.last_used_proxy,
            "expires": self.expires,
            "flags": self.type.value
        }


@dataclass(slots=True, frozen=True)
class UserPreference:
    public_description: bool
    public_trigger: bool
    public_metadata: bool
    public_proxy_tags: bool
    public_list: bool
    public_forms: bool
    public_pronouns: bool
    public_spotlight: bool
    dice_functions: bytes
    spotlight: Sequence[ID]

    @classmethod
    def from_database(cls, row: Row) -> UserPreference:
        return cls(
            public_description = not bool(row["private_description"]),
            public_trigger = not bool(row["private_trigger"]),
            public_metadata = not bool(row["private_metadata"]),
            public_proxy_tags = not bool(row["private_proxy_tags"]),
            public_list = not bool(row["private_list"]),
            public_forms = not bool(row["private_forms"]),
            public_pronouns = not bool(row["private_pronouns"]),
            public_spotlight = not bool(row["private_spotlight"]),
            dice_functions = row["dice_functions"],
            spotlight = tuple(ID(id_) for id_ in ((json.loads(row["spotlight"]) or []) if row["spotlight"] else []))
        )


    def to_database(self) -> dict:
        return {
            "private_description": not self.public_description,
            "private_trigger": not self.public_trigger,
            "private_metadata": not self.public_metadata,
            "private_proxy_tags": not self.public_proxy_tags,
            "private_list": not self.public_list,
            "private_forms": not self.public_forms,
            "private_pronouns": not self.public_pronouns,
            "private_spotlight": not self.public_spotlight,
            "dice_functions": self.dice_functions,
            "spotlight": json.dumps(self.spotlight)
        }


    @classmethod
    def default(cls) -> UserPreference:
        return cls(
            True, True, True, True, True, True, True, True, b"", ()
        )


class Cache:
    user_preferences = TTLCache[UserID, UserPreference](4096, 3600)
    autoproxy_preferences = TTLCache[tuple[UserID, GuildDat], AutoproxyPreference](4096, 60)


class UserSettingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database


    async def set_user_preference(self, user: UserID, preferences: UserPreference) -> None:
        async with self.database.connection.execute("""
            INSERT OR REPLACE INTO user_settings (
                user_id,
                private_description, private_trigger, private_metadata, private_proxy_tags,
                private_list, private_forms, private_pronouns, private_spotlight,
                dice_functions, spotlight
            ) VALUES (
                :id,
                :private_description, :private_trigger, :private_metadata, :private_proxy_tags,
                :private_list, :private_forms, :private_pronouns, :private_spotlight,
                :dice_functions, :spotlight
            )
        """, preferences.to_database() | {
            "id": user
        }):
            Cache.user_preferences.invalidate(user)


    async def get_user_preference(self, user: UserID) -> UserPreference:
        if dat := Cache.user_preferences.get(user):
            return dat

        async with self.database.connection.execute("""
            SELECT * FROM user_settings WHERE user_id = ?
        """, (user,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                prefs = UserPreference.default()
            else:
                prefs = UserPreference.from_database(row)
            Cache.user_preferences.set(user, prefs)
            return prefs


    async def get_autoproxy_preference(self, user: UserID, guild: GuildDat) -> AutoproxyPreference | None:
        if dat := Cache.autoproxy_preferences.get((user, guild)):
            if dat.do_expire_now():
                Cache.autoproxy_preferences.invalidate((user, guild))
                return None
            return dat

        async with self.database.connection.execute("""
            SELECT * FROM autoproxies
            WHERE guild_id = :guild_id AND user_id = :user_id AND guild_type = :guild_type
        """, {
            "guild_id": guild.guild_id,
            "user_id": user,
            "guild_type": guild.platform.get()
        }) as cursor:
            row = await cursor.fetchone()
            if row is None: return None
            preferences = AutoproxyPreference.from_database(row)
            Cache.autoproxy_preferences.set((user, guild), preferences)
            return preferences


    async def get_effective_autoproxy_preference(self, user: UserID, guild: GuildDat) -> AutoproxyPreference | None:
        if local_ap := await self.get_autoproxy_preference(user, guild):
            return local_ap
        return await self.get_autoproxy_preference(user, GuildDat(0, guild.platform))


    async def cleanup_expired_autoproxy(self) -> None:
        async with self.database.connection.execute("""
            DELETE FROM autoproxies WHERE expires <= ? RETURNING guild_id, guild_type, user_id
        """, (time.time(),)) as cursor:
            for row in await cursor.fetchall():
                key = (
                    UserID(row["user_id"]),
                    GuildDat(
                        row["guild_id"],
                        Platform.from_(row["guild_type"])
                    )
                )
                Cache.autoproxy_preferences.invalidate(key)


    async def set_autoproxy_preference(self, user: UserID, preferences: AutoproxyPreference) -> None:
        async with self.database.connection.execute("""
            INSERT OR REPLACE INTO autoproxies (
                guild_id, user_id, proxy, last_used_proxy, expires, guild_type, flags
            ) VALUES (
                :guild_id, :user_id, :proxy, :last_used_proxy, :expires, :guild_type, :flags
            )
        """, {
            "user_id": user,
        } | preferences.to_database()):
            Cache.autoproxy_preferences.invalidate((user, preferences.matched_guild))


    async def remove_single_autoproxy_preference(self, user: UserID, guild: GuildDat) -> None:
        async with self.database.connection.execute("""
            DELETE FROM autoproxies
            WHERE guild_id = :guild_id AND user_id = :user_id AND guild_type = :guild_type
        """, {
            "user_id": user,
            "guild_id": guild.guild_id,
            "guild_type": guild.platform.get()
        }):
            Cache.autoproxy_preferences.invalidate((user, guild))


    async def remove_all_autoproxy_preference(self, user: UserID) -> None:
        async with self.database.connection.execute("""
            DELETE FROM autoproxies WHERE user_id = ? RETURNING guild_id, guild_type
        """, (user,)) as cursor:
            for row in await cursor.fetchall():
                key = (
                    user,
                    GuildDat(
                        row["guild_id"],
                        Platform.from_(row["guild_type"])
                    )
                )
                Cache.autoproxy_preferences.invalidate(key)


    async def delete_account(self, user: UserID) -> None:
        await self.database.connection.execute(
            """
            DELETE FROM user_settings WHERE user_id = ?
            """,
            (user,)
        )
        Cache.user_preferences.invalidate(user)
        await self.remove_all_autoproxy_preference(user)


from dataclasses import dataclass
from enum import IntFlag, IntEnum
from typing import TYPE_CHECKING

from ..cache import TTLCache
from ..models import GuildDat

if TYPE_CHECKING:
    from .database import Database


class GuildPermissions(IntFlag):
    PROXYING = 1 << 0
    EMBED_BLOCKS = 1 << 1
    MULTIPROXY = 1 << 2
    DICE = 1 << 3

    @classmethod
    def all(cls) -> GuildPermissions:
        return cls.PROXYING | cls.EMBED_BLOCKS | cls.MULTIPROXY | cls.DICE


GUILD_PERMISSION_DISPLAY: dict[GuildPermissions, str] = {
    GuildPermissions.PROXYING: "proxy",
    GuildPermissions.EMBED_BLOCKS: "embed",
    GuildPermissions.MULTIPROXY: "multiproxy",
    GuildPermissions.DICE: "dice"
}
DISPLAY_GUILD_PERMISSION: dict[str, GuildPermissions] = {
    v: k
    for k, v in GUILD_PERMISSION_DISPLAY.items()
}


class IDType(IntEnum):
    CHANNEL = 0
    ROLE = 1
    USER = 2
    BASE = 3


@dataclass(slots=True)
class AllowDenyPair:
    allows: GuildPermissions
    denies: GuildPermissions

    def apply(self, permissions: GuildPermissions) -> GuildPermissions:
        return GuildPermissions(permissions.value & (~self.denies.value) | self.allows.value)

    @classmethod
    def default(cls) -> AllowDenyPair:
        return AllowDenyPair(GuildPermissions(0), GuildPermissions(0))

    @classmethod
    def base(cls) -> AllowDenyPair:
        return AllowDenyPair(GuildPermissions.all(), GuildPermissions(0))


type IDMap = dict[int, AllowDenyPair]


class Cache:
    permissions = TTLCache[tuple[int, IDType, GuildDat], AllowDenyPair](4096, 3600)
    guild_overrides = TTLCache[GuildDat, dict[IDType, IDMap]](1024, 3600)


class PermissionsRepository:
    def __init__(self, database: Database):
        self.database = database


    async def override(self, id_: int, id_type: IDType, guild: GuildDat, perms: AllowDenyPair) -> None:
        async with self.database.connection.execute(
            """
            INSERT OR REPLACE INTO permission_overrides (
                guild_id, guild_type, id, id_type, allows, denies
            ) VALUES (
                :guild_id, :guild_type, :id, :id_type, :allows, :denies
            )
            """,
                {
                    "guild_id": guild.guild_id,
                    "guild_type": guild.platform.get(),
                    "id": id_,
                    "id_type": id_type.value,
                    "allows": perms.allows.value,
                    "denies": perms.denies.value,
                }
        ):
            Cache.permissions.invalidate((id_, id_type, guild))
            Cache.guild_overrides.invalidate(guild)


    async def remove_override(self, id_: int, id_type: IDType, guild: GuildDat) -> None:
        async with self.database.connection.execute(
            """
            DELETE FROM permission_overrides WHERE
                guild_id = :guild_id AND
                guild_type = :guild_type AND
                id = :id AND
                id_type = :id_type
            """,
                {
                    "guild_id": guild.guild_id,
                    "guild_type": guild.platform.get(),
                    "id": id_,
                    "id_type": id_type.value,
                }
        ):
            Cache.permissions.invalidate((id_, id_type, guild))
            Cache.guild_overrides.invalidate(guild)


    async def get_override(self, id_: int, id_type: IDType, guild: GuildDat) -> AllowDenyPair:
        if dat := Cache.permissions.get((id_, id_type, guild)):
            return dat

        async with self.database.connection.execute(
            """
            SELECT allows, denies FROM permission_overrides WHERE
                guild_id = :guild_id AND
                guild_type = :guild_type AND
                id = :id AND
                id_type = :id_type
            """,
                {
                    "guild_id": guild.guild_id,
                    "guild_type": guild.platform.get(),
                    "id": id_,
                    "id_type": id_type.value,
                }
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                d = AllowDenyPair(
                    GuildPermissions(0),
                    GuildPermissions(0)
                )
            else:
                d = AllowDenyPair(
                    GuildPermissions(row["allows"]),
                    GuildPermissions(row["denies"])
                )
            Cache.permissions.set((id_, id_type, guild), d)
            return d


    async def get_all_guild_overrides(self, guild: GuildDat) -> dict[IDType, IDMap]:
        if dat := Cache.guild_overrides.get(guild):
            return dat

        async with self.database.connection.execute(
            """
            SELECT id, id_type, allows, denies FROM permission_overrides WHERE
                guild_id = :guild_id AND
                guild_type = :guild_type
            """,
                {
                    "guild_id": guild.guild_id,
                    "guild_type": guild.platform.get(),
                }
        ) as cursor:
            overrides: dict[IDType, IDMap] = {
                IDType.BASE: {0: AllowDenyPair.base()},
                IDType.CHANNEL: {},
                IDType.ROLE: {},
                IDType.USER: {},
            }
            for row in await cursor.fetchall():
                overrides[IDType(row["id_type"])][row["id"]] = AllowDenyPair(
                    GuildPermissions(row["allows"]),
                    GuildPermissions(row["denies"])
                )
            Cache.guild_overrides.set(guild, overrides)
            return overrides


    async def remove_all_overrides(self, guild: GuildDat) -> None:
        async with self.database.connection.execute(
            """
            DELETE FROM permission_overrides WHERE
                guild_id = :guild_id AND
                guild_type = :guild_type
            RETURNING id, id_type
            """,
            {
                "guild_id": guild.guild_id,
                "guild_type": guild.platform.get()
            }
        ) as cursor:
            for row in await cursor.fetchall():
                Cache.permissions.invalidate((row["id"], IDType(row["id_type"]), guild))
            Cache.guild_overrides.invalidate(guild)


    async def compute_effective_permissions(
            self,
            guild: GuildDat,
            channel: int,
            user: int,
            roles: list[int]
    ) -> GuildPermissions:
        overrides = await self.get_all_guild_overrides(guild)
        channel_overrides = overrides[IDType.CHANNEL].get(channel, AllowDenyPair.default())
        user_overrides = overrides[IDType.USER].get(user, AllowDenyPair.default())

        calc = overrides[IDType.BASE].get(0, AllowDenyPair.base()).apply(GuildPermissions.all())
        calc = channel_overrides.apply(calc)
        for role in roles:
            if role in overrides[IDType.ROLE]:
                calc = overrides[IDType.ROLE][role].apply(calc)
        calc = user_overrides.apply(calc)

        return calc

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .user import SSOID, UserID
from ..cache import TTLCache
from ..models import ID, MessageDat, GuildDat, Platform

if TYPE_CHECKING:
    from .database import Database


__all__ = "GuildRepository", "MessageLink", "GuildPreference"


@dataclass(slots=True, frozen=True)
class MessageLink:
    dat: MessageDat
    proxy_id: ID
    platform_user: SSOID


@dataclass(slots=True, frozen=True)
class GuildPreference:
    dat: GuildDat
    logging_channel: int
    dice_functions: bytes

    @classmethod
    def default(cls, guild: GuildDat) -> GuildPreference:
        return cls(
            guild,
            0,
            b""
        )


class Cache:
    guild_preferences = TTLCache[GuildDat, GuildPreference](2500, 3600)
    channel_webhooks = TTLCache[tuple[int, Platform], int](4096, 3600)



class GuildRepository:
    def __init__(self, database: Database) -> None:
        self.database = database


    async def link_message(self, link: MessageLink) -> None:
        await self.database.connection.execute("""
            INSERT INTO message_links (
                message_id, channel_id, proxy_id, platform_user, platform_type
            ) VALUES (
                :message_id, :channel_id, :proxy_id, :platform_user, :platform_type
            )
        """, {
            "message_id": link.dat.message_id,
            "channel_id": link.dat.channel_id,
            "proxy_id": link.proxy_id,
            "platform_user": link.platform_user,
            "platform_type": link.dat.platform.get()
        })


    async def delete_link_message(self, message: MessageDat) -> None:
        await self.database.connection.execute("""
            DELETE FROM message_links WHERE
                message_id = :message_id AND channel_id = :channel_id AND
                platform_type = :platform_type
        """, {
            "message_id": message.message_id,
            "channel_id": message.channel_id,
            "platform_type": message.platform.get()
        })


    async def get_message_link(self, message: MessageDat) -> MessageLink | None:
        async with self.database.connection.execute("""
            SELECT * FROM message_links WHERE
                message_id = :message_id AND channel_id = :channel_id AND
                platform_type = :platform_type
        """, {
            "message_id": message.message_id,
            "channel_id": message.channel_id,
            "platform_type": message.platform.get()
        }) as cursor:
            row = await cursor.fetchone()
            if row is None: return None
            return MessageLink(
                MessageDat(
                    message.message_id,
                    message.channel_id,
                    message.platform
                ),
                ID(row["proxy_id"]),
                SSOID(row["platform_user"])
            )


    async def latest_message_link_from_user(
            self,
            channel_id: int,
            platform: Platform,
            user: UserID
    ) -> MessageLink | None:
        async with self.database.connection.execute("""
            SELECT message_link.* FROM message_links message_link
                JOIN proxies proxy ON
                    message_link.proxy_id = proxy.id
                WHERE
                    message_link.channel_id = :channel_id AND
                    message_link.platform_type = :platform_type AND
                    proxy.owner = :user
                ORDER BY message_link.message_id DESC LIMIT 1
        """, {
            "channel_id": channel_id,
            "platform_type": platform.get(),
            "user": user
        }) as cursor:
            row = await cursor.fetchone()
            if row is None: return None
            return MessageLink(
                MessageDat(
                    row["message_id"],
                    channel_id,
                    platform
                ),
                ID(row["proxy_id"]),
                SSOID(row["platform_user"])
            )


    async def set_guild_preferences(self, prefs: GuildPreference) -> None:
        async with self.database.connection.execute("""
            INSERT OR REPLACE INTO guild_preferences (
                guild_id, logging_channel, dice_functions, guild_type
            ) VALUES (
                :guild_id, :logging_channel, :dice_functions, :guild_type
            )
        """, {
            "guild_id": prefs.dat.guild_id,
            "logging_channel": prefs.logging_channel,
            "dice_functions": prefs.dice_functions,
            "guild_type": prefs.dat.platform.get()
        }):
            Cache.guild_preferences.invalidate(GuildDat(prefs.dat.guild_id, prefs.dat.platform))


    async def get_guild_preferences(self, guild: GuildDat) -> GuildPreference:
        if dat := Cache.guild_preferences.get(guild):
            return dat

        async with self.database.connection.execute("""
            SELECT * FROM guild_preferences WHERE
                guild_id = ? AND guild_type = ?
        """, (guild.guild_id, guild.platform.get())) as cursor:
            row = await cursor.fetchone()
            if not row:
                prefs = GuildPreference.default(guild)
            else:
                prefs = GuildPreference(
                    guild,
                    row["logging_channel"],
                    row["dice_functions"]
                )
            Cache.guild_preferences.set(guild, prefs)
            return prefs


    async def put_channel_webhook(
            self,
            channel_id: int,
            platform: Platform,
            webhook_id: int
    ) -> None:
        async with self.database.connection.execute("""
            INSERT OR REPLACE INTO channel_webhook_map (
                channel_id, webhook_id, guild_type
            ) VALUES (
                :channel_id, :webhook_id, :guild_type
            )
        """, {
            "channel_id": channel_id,
            "webhook_id": webhook_id,
            "guild_type": platform.get()
        }):
            Cache.channel_webhooks.invalidate((channel_id, platform))


    async def get_channel_webhook(
            self,
            channel_id: int,
            platform: Platform
    ) -> int | None:
        if dat := Cache.channel_webhooks.get((channel_id, platform)):
            return dat

        async with self.database.connection.execute("""
            SELECT webhook_id FROM channel_webhook_map WHERE channel_id = :channel_id AND guild_type = :guild_type
        """, {
            "channel_id": channel_id,
            "guild_type": platform.get()
        }) as cursor:
            row = await cursor.fetchone()
            if row is None: return None
            Cache.channel_webhooks.set((channel_id, platform), row["webhook_id"])
            return row["webhook_id"]

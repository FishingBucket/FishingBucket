from typing import TYPE_CHECKING

from ..cache import TTLCache
from ..models import ID

if TYPE_CHECKING:
    from .user import UserID
    from .database import Database

__all__ = "RelationshipRepository",


class Cache:
    proxy_tags = TTLCache[ID, list[ID]](4096, 3600) # proxy -> tags[]


class RelationshipRepository:
    def __init__(self, database: Database):
        self.database = database


    async def set_relationship(self, proxy: ID, tags: list[ID]) -> None:
        await self.database.connection.execute("""
            DELETE FROM proxy_tags_map WHERE proxy_id = ?
        """, (proxy,))
        async with self.database.connection.executemany("""
            INSERT INTO proxy_tags_map (
                proxy_id, tag_id
            ) VALUES (?, ?)
        """, [(proxy, tag) for tag in tags]):
            Cache.proxy_tags.invalidate(proxy)


    async def get_relationships(self, proxy: ID) -> list[ID]:
        if dat := Cache.proxy_tags.get(proxy):
            return dat

        async with self.database.connection.execute("""
            SELECT tag_id FROM proxy_tags_map WHERE proxy_id = ?
        """, (proxy,)) as cursor:
            ids = [ID(row["tag_id"]) for row in await cursor.fetchall()]
            Cache.proxy_tags.set(proxy, ids)
            return ids


    async def get_proxies_for(self, tag: ID) -> list[ID]:
        async with self.database.connection.execute("""
            SELECT proxy_id FROM proxy_tags_map WHERE tag_id = ?
        """, (tag,)) as cursor:
            ids = [ID(row["proxy_id"]) for row in await cursor.fetchall()]
            return ids


    async def bulk_get_relationships(self, proxies: list[ID]) -> dict[ID, list[ID]]:
        return {
            id_: await self.get_relationships(id_)
            for id_ in proxies
        }


    async def bulk_get_backward_relationships(self, tags: list[ID]) -> dict[ID, list[ID]]:
        return {
            id_: await self.get_proxies_for(id_)
            for id_ in tags
        }


    async def nuke(self, user: UserID) -> None:
        async with self.database.connection.execute(
            """
            DELETE FROM proxy_tags_map WHERE proxy_id IN (
                SELECT id FROM proxies WHERE owner = ?
            ) RETURNING proxy_id
            """,
                (user,)
        ) as cursor:
            for row in await cursor.fetchall():
                Cache.proxy_tags.invalidate(ID(row["proxy_id"]))


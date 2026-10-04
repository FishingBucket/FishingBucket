from typing import TYPE_CHECKING

from .user import UserID
from ..cache import TTLCache
from ..models import ID, ProxyTag

if TYPE_CHECKING:
    from .database import Database

__all__ = "ProxyTagRepository",


class Cache:
    tag_from_id = TTLCache[ID, ProxyTag](4096, 3600)
    tags_from_user = TTLCache[UserID, list[ID]](1024, 3600)


class ProxyTagRepository:
    def __init__(self, database: Database):
        self.database = database


    async def put(self, tag: ProxyTag) -> ID:
        async with self.database.connection.execute("""
            INSERT INTO proxy_tags (
                name, description, owner, creation_date, tag
            ) VALUES (
                :name, :description, :owner, :creation_date, :tag
            ) RETURNING id
        """, tag.to_primitive_dict()) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            tag_id = ID(row["id"])
            tag.id = tag_id
            Cache.tags_from_user.invalidate(tag.owner)
            return tag_id


    async def update(self, tag: ProxyTag) -> None:
        async with self.database.connection.execute("""
            UPDATE proxy_tags SET
                name = :name, description = :description,
                creation_date = :creation_date, tag = :tag
            WHERE id = :id
        """, tag.to_primitive_dict()):
            Cache.tag_from_id.invalidate(tag.id)


    async def delete(self, tag_id: ID) -> None:
        async with self.database.connection.execute("""
            DELETE FROM proxy_tags WHERE id = ? RETURNING owner
        """, (tag_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None: return
            Cache.tag_from_id.invalidate(tag_id)
            Cache.tags_from_user.invalidate(UserID(row["owner"]))


    async def get(self, tag_id: ID) -> ProxyTag | None:
        if dat := Cache.tag_from_id.get(tag_id):
            return dat

        async with self.database.connection.execute("""
            SELECT * FROM proxy_tags WHERE id = ?
        """, (tag_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None: return None
            tag = ProxyTag.from_database(row)
            Cache.tag_from_id.set(tag_id, tag)
            return tag


    async def from_user(self, user: UserID) -> list[ProxyTag]:
        return await self.fetch_bulk(await self.tag_ids_from_user(user))


    async def fetch_bulk(self, tag_ids: list[ID]) -> list[ProxyTag]:
        tags: list[ProxyTag] = []
        for id_ in tag_ids:
            tag = await self.get(id_)
            if tag:
                tags.append(tag)
        return tags


    async def tag_ids_from_user(self, user: UserID) -> list[ID]:
        if dat := Cache.tags_from_user.get(user):
            return dat

        async with self.database.connection.execute("""
            SELECT id FROM proxy_tags WHERE owner = ? ORDER BY id ASC
        """, (user,)) as cursor:
            ids = [ID(row["id"]) for row in await cursor.fetchall()]
            Cache.tags_from_user.set(user, ids)
            return ids


    async def exists(self, tag_id: ID) -> bool:
        async with self.database.connection.execute("""
            SELECT COUNT(*) FROM proxy_tags WHERE id = ?
        """, (tag_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None: return False
            return bool(row[0])


    async def get_member_count(self, tag_id: int) -> int:
        async with self.database.connection.execute("""
            SELECT COUNT(*) AS member_count FROM proxy_tags_map WHERE tag_id = ?
        """, (tag_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None: return 0
            return row["member_count"]


    async def nuke(self, user: UserID) -> None:
        async with self.database.connection.execute(
            """
            DELETE FROM proxy_tags WHERE owner = ?
            RETURNING id
            """,
                (user,)
        ) as cursor:
            for row in await cursor.fetchall():
                Cache.tag_from_id.invalidate(ID(row["id"]))

        Cache.tags_from_user.invalidate(user)

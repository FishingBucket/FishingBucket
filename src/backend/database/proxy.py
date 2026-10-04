from typing import TYPE_CHECKING

from .user import UserID
from ..cache import TTLCache
from ..models import ID, Proxy, FullProxy

if TYPE_CHECKING:
    from .database import Database

__all__ = "ProxyRepository"


class Cache:
    proxy_from_id = TTLCache[ID, Proxy](4096, 3600)
    proxies_from_user = TTLCache[UserID, list[ID]](1024, 3600)
    proxies_from_user_with_triggers = TTLCache[UserID, list[ID]](1024, 3600)


class ProxyRepository:
    def __init__(self, database: Database) -> None:
        self.database = database


    async def put(self, proxy: FullProxy) -> ID:
        await self.database.set_global_data("total_proxies", "value + 1", 0)
        async with self.database.connection.execute("""
            INSERT INTO proxies (
                name, description, avatar_url, triggers, owner, times_used, creation_date, nickname, proxy_forms, current_form, pronouns
            ) VALUES (
                :name, :description, :avatar_url, :triggers, :owner, :times_used, :creation_date, :nickname, :proxy_forms, :current_form, :pronouns
            ) RETURNING id
        """, proxy.to_primitive_dict()) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            proxy_id = ID(row["id"])
            proxy.id = proxy_id
            Cache.proxies_from_user.invalidate(proxy.owner)
            return proxy_id


    async def update(self, proxy: FullProxy) -> None:
        async with self.database.connection.execute("""
            UPDATE proxies SET
                name = :name, description = :description, avatar_url = :avatar_url, triggers = :triggers, owner = :owner,
                times_used = :times_used, creation_date = :creation_date, nickname = :nickname, proxy_forms = :proxy_forms,
                current_form = :current_form, pronouns = :pronouns
            WHERE id = :id
        """, proxy.to_primitive_dict()):
            Cache.proxy_from_id.invalidate(proxy.id)


    async def get_uses(self, proxy_id: ID) -> int:
        async with self.database.connection.execute("""
            SELECT times_used FROM proxies WHERE id = ?
        """, (proxy_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return 0
            uses = row["times_used"]
            return uses


    async def use(self, proxy_id: ID) -> None:
        await self.database.connection.execute("""
            UPDATE proxies SET
                times_used = times_used + 1
            WHERE id = ?
        """, (proxy_id,))
        await self.database.set_global_data("proxy_uses", "value + 1", 1)


    async def transfer_usage(self, old_proxy: ID, new_proxy: ID) -> None:
        await self.database.connection.execute("""
            UPDATE proxies SET
                times_used = times_used - 1
            WHERE id = ?;
        """, (old_proxy,))
        await self.database.connection.execute("""
            UPDATE proxies SET
                times_used = times_used + 1
            WHERE id = ?;
        """, (new_proxy,))


    async def delete(self, proxy_id: ID) -> None:
        await self.database.set_global_data("total_proxies", "value - 1", 0)
        async with self.database.connection.execute("""
            DELETE FROM proxies WHERE id = ? RETURNING owner
        """, (proxy_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None: return
            Cache.proxy_from_id.invalidate(proxy_id)
            Cache.proxies_from_user.invalidate(UserID(row["owner"]))


    async def get(self, proxy_id: ID) -> Proxy | None:
        if dat := Cache.proxy_from_id.get(proxy_id):
            return dat

        async with self.database.connection.execute("""
            SELECT * FROM proxies WHERE id = ?
        """, (proxy_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None: return None
            proxy = FullProxy.from_database(row)
            nonvolatile_proxy = Proxy.from_full(proxy)
            Cache.proxy_from_id.set(proxy_id, nonvolatile_proxy)
            return nonvolatile_proxy


    async def from_user(self, user: UserID) -> list[Proxy]:
        return await self.fetch_bulk(await self.proxy_ids_from_user(user))


    async def from_user_with_triggers(self, user: UserID) -> list[Proxy]:
        return await self.fetch_bulk(await self.proxy_ids_from_user_with_triggers(user))


    async def full_from_user(self, user: UserID) -> list[FullProxy]:
        return await self.fetch_bulk_full(await self.proxy_ids_from_user(user))


    async def fetch_bulk(self, proxy_ids: list[ID]) -> list[Proxy]:
        proxies: list[Proxy] = []
        for id_ in proxy_ids:
            proxy = await self.get(id_)
            if proxy:
                proxies.append(proxy)
        return proxies


    async def fetch_bulk_full(self, proxy_ids: list[ID]) -> list[FullProxy]:
        proxies: list[FullProxy] = []
        for id_ in proxy_ids:
            proxy = await self.get_full(id_)
            if proxy:
                proxies.append(proxy)
        return proxies


    async def proxy_ids_from_user(self, user: UserID) -> list[ID]:
        if dat := Cache.proxies_from_user.get(user):
            return dat

        async with self.database.connection.execute("""
            SELECT id FROM proxies WHERE owner = ? ORDER BY id ASC
        """, (user,)) as cursor:
            ids = [ID(row["id"]) for row in await cursor.fetchall()]
            Cache.proxies_from_user.set(user, ids)
            return ids


    async def proxy_ids_from_user_with_triggers(self, user: UserID) -> list[ID]:
        if dat := Cache.proxies_from_user_with_triggers.get(user):
            return dat

        async with self.database.connection.execute("""
            SELECT id FROM proxies WHERE owner = ? AND triggers != '' ORDER BY id ASC
        """, (user,)) as cursor:
            ids = [ID(row["id"]) for row in await cursor.fetchall()]
            Cache.proxies_from_user_with_triggers.set(user, ids)
            return ids


    async def get_full(self, proxy_id: ID) -> FullProxy | None:
        async with self.database.connection.execute("""
            SELECT * FROM proxies WHERE id = ?
        """, (proxy_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            proxy = FullProxy.from_database(row)
            return proxy


    async def exists(self, proxy_id: ID) -> bool:
        async with self.database.connection.execute("""
            SELECT COUNT(*) FROM proxies WHERE id = ?
        """, (proxy_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None: return False
            return bool(row[0])


    async def nuke(self, user: UserID) -> None:
        amount = 0

        async with self.database.connection.execute(
            """
            DELETE FROM proxies WHERE owner = ?
            RETURNING id
            """,
                (user,)
        ) as cursor:
            for row in await cursor.fetchall():
                Cache.proxy_from_id.invalidate(ID(row["id"]))
                amount += 1

        Cache.proxies_from_user.invalidate(user)

        await self.database.set_global_data("total_proxies", f"value - {amount}", 0)


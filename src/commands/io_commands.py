import json

import pydantic
from aiohttp import ClientSession

from .generic import hook_command
from .specific import get_uid, get_or_make_uid
from ..backend.database.database import get_db
from ..backend.import_system import NativeImporter, TupperboxImporter, PluralKitImporter, UtterImporter, NativeExporter, \
    Importer, PluRalImporter, PluralBuddyImporter
from ..backend.logging import start_log
from ..backend.models import ProxyTag, Proxy, ID
from ..service import Context, Embed, File

print, error = start_log("im/exporter")


def setup():
    @hook_command("import")
    async def _(context: Context, file: str | None, origin: str | None):
        if not context.message.attachments and not file:
            await context.reply("Error: no import file found.")
            return

        if file:
            filename = file.split("?")[0].split("/")[-1]
            async with ClientSession() as session:
                async with session.get(file) as response:
                    contents = await response.read()
        else:
            filename = context.message.attachments[0].filename
            contents = await context.message.attachments[0].read()

        origin = origin or (
            "fishing_bucket" if "fishing" in filename and "bucket" in filename and filename.endswith(".json") else
            "tupperbox" if "tupper" in filename and filename.endswith(".json") else
            "pluralkit" if "system" in filename and filename.endswith(".json") else
            "utter" if "utter" in filename and filename.endswith(".json") else
            "/plu/ral" if "plural" in filename and filename.endswith(".json") else
            None
        )

        if origin is None:
            await context.reply(f"Error: cannot guess import file origin with the filename {filename!r}.")
            return

        origin_names = {
            "fishing_bucket": "Fishing Bucket",
            "tupperbox": "Tupperbox",
            "pluralkit": "PluralKit",
            "utter": "Utter",
            "/plu/ral": "/plu/ral",
            "pluralbuddy": "PluralBuddy"
        }

        confirmation = await context.reply(f"Importing from {origin_names[origin]}")
        try:
            await context.message.delete()
        except: pass

        owner = await get_or_make_uid(context)

        cls: Importer

        if origin == "fishing_bucket":
            cls = NativeImporter()
        elif origin == "tupperbox":
            cls = TupperboxImporter()
        elif origin == "pluralkit":
            cls = PluralKitImporter()
        elif origin == "utter":
            cls = UtterImporter()
        elif origin == "/plu/ral":
            cls = PluRalImporter()
        elif origin == "pluralbuddy":
            cls = PluralBuddyImporter()
        else:
            raise Exception("unreachable")

        try:
            cls.import_data(contents, owner)
        except (json.JSONDecodeError, pydantic.ValidationError) as e:
            error(e)
            await confirmation.reply(f"Error: cannot parse file")
            return

        user_proxies = await get_db().proxies.from_user(owner)
        user_tags = await get_db().tags.from_user(owner)
        user_relationships = await get_db().relationships.bulk_get_relationships([proxy.id for proxy in user_proxies])

        updated_proxies = 0
        updated_tags = 0

        inserted_proxy_instances: list[Proxy] = []
        inserted_tag_instances: list[ProxyTag] = []

        tag_mapping: dict[ID, ID] = {}
        proxy_mapping: dict[ID, ID] = {}

        async with get_db().transaction():
            for tag in cls.tags:
                found_tag = [t for t in user_tags if t.name == tag.name]
                if found_tag:
                    db_tag = found_tag[0]
                    assert db_tag.id is not None

                    await get_db().tags.update(tag)
                    updated_tags += 1
                else:
                    tag_mapping[tag.id] = await get_db().tags.put(tag)
                    inserted_tag_instances.append(tag)

            for proxy in cls.proxies:
                found_proxy = [p for p in user_proxies if p.name == proxy.name]
                if found_proxy:
                    db_proxy = found_proxy[0]
                    assert db_proxy.id is not None

                    await get_db().proxies.update(proxy)
                    updated_proxies += 1
                else:
                    proxy_mapping[proxy.id] = await get_db().proxies.put(proxy)
                    inserted_proxy_instances.append(proxy)

            for relation_proxy, relation_tags in cls.relationships.items():
                remapped_proxy = proxy_mapping[relation_proxy]
                remapped_tags = [tag_mapping[t] for t in relation_tags]
                if remapped_proxy in user_relationships and user_relationships[remapped_proxy] == remapped_tags:
                    continue
                await get_db().relationships.set_relationship(remapped_proxy, remapped_tags)

        inserted_proxies = len(inserted_proxy_instances)
        inserted_tags = len(inserted_tag_instances)

        await confirmation.message.edit(
            f"Proxies loaded! Updated {updated_proxies} proxies and {updated_tags} tags, and inserted {inserted_proxies} new proxies and {inserted_tags} new tags!")

        proxies_text = "\n".join(
            f"- **{p.name}** (`{p.id}`)" for p in inserted_proxy_instances[:min(len(inserted_proxy_instances), 20)]
        ) or "- No proxies were added!"

        if len(inserted_proxy_instances) > 20:
            proxies_text += f"\n...... and {len(inserted_proxy_instances) - 20} more"

        tags_text = "\n".join(
            f"- **{t.name}** (`{t.id}`)" for t in inserted_tag_instances[:min(len(inserted_tag_instances), 20)]
        ) or "- No tags were added!"

        if len(inserted_tag_instances) > 20:
            tags_text += f"\n...... and {len(inserted_tag_instances) - 20} more"

        await confirmation.reply("", embeds=[
            Embed(
                f"{context.author.display_name}'s New Imports",
                f"New proxies:\n{proxies_text}\n\nNew tags:\n{tags_text}"
            )
        ])


    @hook_command("export")
    async def _(context: Context):
        owner = await get_uid(context)
        tags = await get_db().tags.from_user(owner)
        proxies = await get_db().proxies.full_from_user(owner)
        relationships = await get_db().relationships.bulk_get_relationships([proxy.id for proxy in proxies])
        exporter = NativeExporter(proxies, tags, relationships)
        file = File(
            exporter.filename,
            "",
            exporter.export_data()
        )

        channel = await context.get_this_channel()
        if not channel.dm:
            dm = await context.author.get_dm()
            await dm.send("Proxies exported!", files=[file])
            await context.reply("I've sent your exported proxies into your DM!")
        else:
            await context.reply("Proxies exported!", files=[file])

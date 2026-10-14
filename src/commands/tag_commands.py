import time
from dataclasses import replace

from .generic import hook_command
from .specific import get_uid, get_or_make_uid
from .utils import paged_tag_list, get_tag_text, paged_proxy_list
from ..backend.database.database import get_db
from ..backend.models import ProxyTag, Proxy, ID, FullProxy
from ..backend.template_utils import Template
from ..backend.utils import quote, normalize_emojis
from ..interaction import Interactions, Interaction
from ..service import Context, Embed, ReactionActionEvent


def setup():
    @hook_command("tag register")
    async def _(context: Context, name: str, description: str) -> None:
        async with get_db().transaction():
            tag_id = await get_db().tags.put(
                ProxyTag(
                    ID(0),
                    name,
                    description,
                    await get_or_make_uid(context),
                    time.time(),
                    ""
                )
            )

        description_text = ("\nDescription:\n" + quote(description)) if description else ""
        await context.reply("", [Embed(
            "Tag Registered!",
            f"The tag **{name}** (`{tag_id}`) has been registered.{description_text}",
        )])

    @hook_command("tag list")
    async def _(context: Context, page: int, detailed: bool) -> None:
        channel = await context.get_this_channel()
        uid = await get_uid(context)

        tags = await get_db().tags.from_user(uid)

        await paged_tag_list(
            context,
            tags,
            await get_db().relationships.bulk_get_backward_relationships([tag.id for tag in tags]),
            await get_db().user_settings.get_user_preference(uid),
            f"Proxy Tags of {context.author.display_name}",
            page,
            channel.dm or detailed
        )

    @hook_command("tag info")
    async def _(context: Context, tag: ProxyTag, detailed: bool) -> None:
        channel = await context.get_this_channel()
        uid = await get_uid(context)

        await context.reply("", [Embed(
            tag.name,
            get_tag_text(
                tag,
                len(await get_db().relationships.get_proxies_for(tag.id)),
                await get_db().user_settings.get_user_preference(uid),
                channel.dm or detailed
            )
        )])

    @hook_command("tag members")
    async def _(context: Context, tag: ProxyTag, page: int, detailed: bool) -> None:
        channel = await context.get_this_channel()
        uid = await get_uid(context)
        members = await get_db().relationships.get_proxies_for(tag.id)
        proxies = await get_db().proxies.fetch_bulk_full(members)

        await paged_proxy_list(
            context,
            proxies,
            await get_db().tags.from_user(uid),
            await get_db().relationships.bulk_get_backward_relationships([proxy.id for proxy in proxies]),
            await get_db().user_settings.get_user_preference(uid),
            f"Members of {context.author.display_name} in **{tag.name}**",
            page,
            channel.dm or detailed
        )

    @hook_command("tag set name")
    async def _(context: Context, tag: ProxyTag, name: str) -> None:
        async with get_db().transaction():
            await get_db().tags.update(replace(tag, name=name))

        await context.reply("", [Embed(
            f"Tag Updated!",
            f"The name for the previous *{tag.name}* has been changed to **{name}**!"
        )])

    @hook_command("tag set description")
    async def _(context: Context, tag: ProxyTag, description: str) -> None:
        async with get_db().transaction():
            await get_db().tags.update(replace(tag, description=description))

        mod = "changed" if description else "cleared"

        await context.reply("", [Embed(
            f"Tag Updated!",
            f"The description for **{tag.name}** has been {mod}!"
        )])

    @hook_command("tag set marker")
    async def _(context: Context, tag: ProxyTag, marker: Template | None) -> None:
        owner = await get_uid(context)

        if marker:
            t = normalize_emojis(marker.string)
            new_tag = replace(tag, tag=t)

            async with get_db().transaction():
                await get_db().tags.update(new_tag)

            example_proxy = FullProxy(
                ID(0),
                "Example Proxy",
                "This is an example proxy.",
                Proxy.random_avatar(),
                ["{}"],
                owner,
                time.time(),
                "Proxy",
                {},
                "",
                "pronoun",
                0
            )
            description = f"The marker for **{tag.name}** has been changed! Proxies with this tag, when sent, will display as *{example_proxy.effective_name([new_tag])}*"
        else:
            async with get_db().transaction():
                await get_db().tags.update(replace(tag, tag=""))

            description = f"The marker for **{tag.name}** has been cleared!"

        await context.reply("", [Embed(
            "Tag Updated!",
            description
        )])

    @hook_command("tag delete")
    async def _(context: Context, tag: ProxyTag) -> None:
        m = await context.reply(f"> [!WARNING]\n> Are you sure you want to remove tag **{tag.name}**? React to the :white_check_mark: to confirm. This message will expire in 30 seconds.")
        await m.message.add_reaction("✅")

        async def cb(event: ReactionActionEvent) -> bool:
            assert tag.id is not None

            if event.emoji == "✅":
                async with get_db().transaction():
                    await get_db().tags.delete(tag.id)

                await m.reply(f"Successfully removed tag **{tag.name}**!")
                return True
            return False

        Interactions.instance.add_interaction(m, Interaction(context.author.id, cb))

        if await Interactions.instance.wait_claim_after(30, m.id, m.platform):
            await m.message.edit("Tag delete confirmation expired.")
            await m.message.remove_reaction("✅")

from dataclasses import replace
from typing import Literal, Tuple

from .generic import hook_command
from .specific import get_uid
from .utils import example_trigger_text
from ..backend.database.database import get_db
from ..backend.models import FullProxy, ProxyTag
from ..backend.template_utils import Template
from ..backend.utils import normalize_emojis, quote
from ..interaction import Interactions, Interaction
from ..service import Context, ReactionActionEvent, Embed


def setup():
    @hook_command("set avatar")
    async def _(context: Context, proxy: FullProxy, url: str | None):
        if not context.message.attachments:
            avatar_url = url or FullProxy.random_avatar()
        else:
            avatar_url = context.message.attachments[0].url

        async with get_db().transaction():
            await get_db().proxies.update(replace(proxy, avatar_url=avatar_url))

        embed = Embed(
            "Proxy Updated!",
            f"The avatar for **{proxy.name}** has been updated!",
            thumbnail_url=avatar_url
        )
        await context.reply("", [embed])


    @hook_command("set triggers")
    async def _(context: Context, proxy: FullProxy, mode: Literal["set"] | Literal["add"] | Literal["remove"], trigger: Template | None):
        if mode == "add" and trigger is None:
            await context.reply("Error: 'add' mode must have a trigger to add.")
            return

        new_triggers: list[str] = proxy.triggers or []
        if mode == "set":
            if trigger is None: new_triggers = []
            else: new_triggers = [trigger.string]
        elif mode == "remove":
            if trigger is None: new_triggers = []
            if trigger and trigger in proxy.triggers: new_triggers.remove(trigger.string)
        elif mode == "add":
            if trigger:
                new_triggers.append(trigger.string)
                new_triggers = [*set(new_triggers)]

        async with get_db().transaction():
            await get_db().proxies.update(replace(proxy, triggers=new_triggers))

        if new_triggers:
            newest = Template.from_string(new_triggers[-1])
            
            embed = Embed(
                "Proxy Updated!",
                f"The triggers for **{proxy.name}** has been changed to {', '.join('`' + trigger + '`' for trigger in new_triggers)}!\nSay hello with it by typing `{example_trigger_text(newest)}`{' or by other triggers' if len(new_triggers) != 1 else ''}!"
            )
        else:
            embed = Embed(
                "Proxy Updated!",
                f"The triggers for **{proxy.name}** has been removed! You won't be able to use this proxy via a trigger anymore."
            )

        await context.reply("", [embed])


    @hook_command("set name")
    async def _(context: Context, proxy: FullProxy, new_name: str):
        old_name = proxy.name
        new_name = normalize_emojis(new_name)

        async with get_db().transaction():
            await get_db().proxies.update(replace(proxy, name=new_name))

        embed = Embed(
            "Proxy Updated!",
            f"The name for the previous *{old_name}* has been changed to **{new_name}**!"
        )
        await context.reply("", [embed])


    @hook_command("set nickname")
    async def _(context: Context, proxy: FullProxy, new_nickname: str):
        old_name = proxy.name
        new_nickname = normalize_emojis(new_nickname)

        async with get_db().transaction():
            await get_db().proxies.update(replace(proxy, nickname=new_nickname))

        embed = Embed(
            "Proxy Updated!",
            f"The nickname for *{old_name}* has been " + (
                f"changed to **{new_nickname}**!" if new_nickname else "cleared!")
        )
        await context.reply("", [embed])


    @hook_command("set pronouns")
    async def _(context: Context, proxy: FullProxy, new_pronouns: str):
        async with get_db().transaction():
            await get_db().proxies.update(replace(proxy, pronouns=new_pronouns))

        if new_pronouns:
            embed = Embed(
                "Proxy Updated!",
                f"The pronouns for **{proxy.name}** has been changed to **{new_pronouns}**!"
            )
        else:
            embed = Embed(
                "Proxy Updated!",
                f"The pronouns for **{proxy.name}** has been reset!"
            )
        await context.reply("", [embed])


    @hook_command("set description")
    async def _(context: Context, proxy: FullProxy, new_description: str):
        async with get_db().transaction():
            await get_db().proxies.update(replace(proxy, description=new_description))

        if new_description:
            embed = Embed(
                "Proxy Updated!",
                f"The description for {proxy.name} has been changed! New description:\n" +
                quote(new_description)
            )
        else:
            embed = Embed(
                "Proxy Updated!",
                f"The description for {proxy.name} has been cleared!"
            )
        await context.reply("", [embed])


    @hook_command("set tags")
    async def _(context: Context, proxy: FullProxy, mode: Literal["add"] | Literal["remove"], tags: list[ProxyTag]) -> None:
        proxy_tags = (await get_db().relationships.get_relationships(proxy.id))[:]

        if mode == "add":
            for tag in tags:
                if tag not in proxy_tags:
                    proxy_tags.append(tag.id)
        if mode == "remove":
            for tag in tags:
                if tag in proxy_tags:
                    proxy_tags.remove(tag.id)

        mod = "changed" if proxy_tags else "cleared"
        more = ""
        if proxy_tags:
            bulk = await get_db().tags.fetch_bulk(proxy_tags)

            more = f" Tags: **{'**, **'.join(tag.name for tag in bulk)}**"

        async with get_db().transaction():
            await get_db().relationships.set_relationship(proxy.id, proxy_tags)

        await context.reply("", [Embed(
            "Proxy Updated!",
            f"The tags for {proxy.name} has been {mod}!{more}"
        )])


    @hook_command("set forms")
    async def _(context: Context, proxy: FullProxy, mode: Literal["set"] | Literal["add"] | Literal["remove"], form: Tuple[str, str | None] | None):
        if mode == "add" and form is None:
            await context.reply("Error: 'add' mode must have a form to add.")
            return

        avatar_url = None
        if mode in ("add", "set"):
            if form is not None:
                if form[1] is None:
                    if not context.message.attachments:
                        avatar_url = form[1] or FullProxy.random_avatar()
                    else:
                        avatar_url = context.message.attachments[0].url

        forms = proxy.forms
        curr_form = proxy.current_form

        if mode in ("add", "set"):
            if form and avatar_url:
                forms[form[0]] = avatar_url
            else:
                forms = {}
                curr_form = ""
        elif mode == "remove":
            if form:
                if form[0] in forms:
                    forms.pop(form[0])
                    if curr_form == form[0]:
                        curr_form = ""
            else:
                forms = {}

        async with get_db().transaction():
            await get_db().proxies.update(replace(proxy, forms=forms, current_form=curr_form))

        forms_texts = []
        for fname, furl in forms.items():
            text = f"- {fname}: [avatar]({furl})"
            if curr_form == fname:
                text += " (current)"
            forms_texts.append(text)
        forms_text = "\n".join(forms_texts) if forms_texts else "No forms!"

        embed = Embed(
            "Proxy Updated!",
            f"The forms for **{proxy.name}** has been changed! Proxy forms:\n{forms_text}"
        )
        await context.reply("", [embed])


    @hook_command("set current form")
    async def _(context: Context, proxy: FullProxy, form: str):
        effective_name = proxy.effective_name(await get_db().tags.fetch_bulk(await get_db().relationships.get_relationships(proxy.id)))

        if not form:
            async with get_db().transaction():
                await get_db().proxies.update(replace(proxy, current_form=""))

            await context.reply("", [Embed(
                "Proxy Updated!",
                f"The current form for **{effective_name}** has been reset."
            )])
        elif form in proxy.forms:
            async with get_db().transaction():
                await get_db().proxies.update(replace(proxy, current_form=form))

            await context.reply("", [Embed(
                "Proxy Updated!",
                f"The current form for **{effective_name}** has been changed to `{form}`."
            )])
        else:
            await context.reply(f"Error: **{effective_name}** does not have the form `{form}`!")


    @hook_command("remove")
    async def _(context: Context, proxy: FullProxy):
        m = await context.reply(f"> [!WARNING]\n> Are you sure you want to remove **{proxy.name}**? React to the :white_check_mark: to confirm. This message will expire in 30 seconds.")
        await m.message.add_reaction("✅")

        async def cb(event: ReactionActionEvent) -> bool:
            if event.emoji == "✅":
                async with get_db().transaction():
                    await get_db().proxies.delete(proxy.id)

                await m.reply(f"Successfully removed **{proxy.name}**!")
                return True
            return False

        Interactions.instance.add_interaction(m, Interaction(context.author.id, cb))

        if await Interactions.instance.wait_claim_after(30, m.id, m.platform):
            await m.message.edit("Proxy remove confirmation expired.")
            await m.message.remove_reaction("✅")


    @hook_command("nuke")
    async def _(context: Context):
        owner = await get_uid(context)
        proxies = await get_db().proxies.from_user(owner)
        tags = await get_db().tags.from_user(owner)

        if not proxies and not tags:
            await context.reply("You have no proxies nor proxy tags to delete!")
            return

        m = await context.reply(f"> [!CAUTION]\n> Are you sure you want to nuke **all of your {len(proxies)} proxies and {len(tags)} tags**? React to the :white_check_mark: to confirm. This message will expire in 10 seconds.")
        await m.message.add_reaction("✅")

        async def cb(event: ReactionActionEvent) -> bool:
            if event.emoji == "✅":
                async with get_db().transaction():
                    await get_db().nuke(owner)

                await m.reply(f"Successfully nuked your proxies!")
                return True
            return False

        Interactions.instance.add_interaction(m, Interaction(context.author.id, cb, 10))

        if await Interactions.instance.wait_claim_after(10, m.id, context.platform):
            await m.message.edit("Proxy nuke confirmation expired!")
            await m.message.remove_reaction("✅")

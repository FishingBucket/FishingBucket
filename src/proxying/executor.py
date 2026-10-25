from dataclasses import replace
from typing import Literal

from .editing import modify_message
from ..backend.cache import TTLCache
from ..backend.config import Config
from ..backend.database.database import get_db
from ..backend.database.guild import MessageLink
from ..backend.database.permission import GuildPermissions
from ..backend.database.user import UserID
from ..backend.models import Proxy, MessageDat, GuildDat
from ..backend.utils import convert_attachments, quote, DelimitedString
from ..service import Webhook, Context, Attachment, Embed
from ..service.common import AllowedMention, MentionPreference

webhook_cache = TTLCache[int, Webhook](2048, 3600)


async def get_webhook(context: Context) -> Webhook | None:
    if webhook := webhook_cache.get(context.message.channel_id): return webhook
    webhook = None

    effective_channel_id = context.message.channel_id
    this_channel = await context.get_this_channel()

    if this_channel.is_thread and (parent_id := this_channel.parent_id):
        effective_channel_id = parent_id

    if webhook_id := await get_db().guilds.get_channel_webhook(effective_channel_id, context.platform):
        webhook = await context.bot.get_webhook(webhook_id)

    if webhook is None:
        effective_channel = this_channel
        if this_channel.is_thread:
            effective_channel = await context.get_channel(effective_channel_id) # type: ignore # guaranteed i think
            assert effective_channel is not None
        webhook = await effective_channel.create_webhook(Config.instance.webhook)
        if webhook:
            await get_db().guilds.put_channel_webhook(effective_channel_id, context.platform, webhook.id)

    if webhook:
        webhook_cache.set(context.message.channel_id, webhook)
    return webhook


async def send_proxy_message(
        proxy: Proxy,
        message: str,
        context: Context,
        attachments: list[Attachment],
        do_reply: bool,
        permissions: GuildPermissions
) -> tuple[Context, str] | None:
    webhook = await get_webhook(context)
    if not webhook:
        return None

    channel = await context.get_this_channel()

    mention_str: str | Literal[False] = False
    ref = await context.message.get_reference()

    mention_pref = MentionPreference.NO_PREFERENCE
    if ref:
        lnk = await get_db().guilds.get_message_link(MessageDat(ref.id, ref.channel_id, context.platform))
        if lnk and (parent_proxy := await get_db().proxies.get(lnk.proxy_id)):
            mentioned_user = await context.get_member(lnk.platform_user) or await context.get_user(lnk.platform_user)
            mention_pref = mentioned_user.mention_preference if mentioned_user else MentionPreference.NO_PREFERENCE
            mention_str = f"{parent_proxy.name} (<@{lnk.platform_user}>)"
        else:
            try:
                mentioned_user = await ref.member()
            except: # mysterious exception
                mentioned_user = ref.author
            mention_pref = mentioned_user.mention_preference if mentioned_user else MentionPreference.NO_PREFERENCE
            mention_str = ref.author.mention if not ref.author.is_bot else ("@" + ref.author.display_name)

    allowed_mentions = AllowedMention(
        mention_pref != MentionPreference.PREFER_NO_MENTION, # temporary solution rn
        True,
        context.message.mentions_everyone,
        mention_pref != MentionPreference.PREFER_NO_MENTION
    )

    thread_id = channel.id if channel.is_thread else None

    message, embeds = await modify_message(
        proxy.owner,
        await get_db().guilds.get_guild_preferences(GuildDat(channel.guild_id, context.platform)),
        permissions,
        message
    )

    name = proxy.effective_name(await get_db().tags.fetch_bulk(await get_db().relationships.get_relationships(proxy.id)))

    if ref and do_reply:
        return await webhook.reply(
            ref.context, name, proxy.effective_avatar, mention_str, message, embeds,
            files=await convert_attachments(attachments),
            allowed_mentions=allowed_mentions, thread_id=thread_id
        ), name

    return await webhook.send(
        name, proxy.effective_avatar, message, embeds,
        files=await convert_attachments(attachments),
        allowed_mentions=allowed_mentions, thread_id=thread_id
    ), name


async def reproxy(message_link: MessageLink, context: Context, old_proxy: Proxy, new_proxy: Proxy):
    webhook = await get_webhook(context)
    if not webhook:
        return
    if (channel := await context.get_channel(context.message.channel_id)) is None:
        return

    guild = GuildDat(channel.guild_id, context.platform)
    guild_preferences = await get_db().guilds.get_guild_preferences(guild)

    fixed_message = await webhook.get_message_data(context)
    contents = fixed_message.content
    attachments = fixed_message.attachments
    embeds = fixed_message.embeds
    parent_message = await fixed_message.get_reference()

    await context.message.delete()
    await get_db().guilds.delete_link_message(MessageDat(context.message.id, context.channel.id, context.platform))

    name = new_proxy.effective_name(await get_db().tags.fetch_bulk(await get_db().relationships.get_relationships(new_proxy.id)))

    mentions_original = await context.message.mentions_original()
    allowed_mention = AllowedMention(
        mentions_original,
        True,
        context.message.mentions_everyone,
        mentions_original
    )

    thread_id = channel.id if channel.is_thread else None

    if parent_message:
        m = await webhook.reply(
            parent_message.context, name, new_proxy.effective_avatar, False, contents, embeds,
            files=await convert_attachments(attachments), allowed_mentions=allowed_mention, thread_id=thread_id
        )
    else:
        m = await webhook.send(
            name, new_proxy.effective_avatar, contents, embeds,
            files=await convert_attachments(attachments), allowed_mentions=allowed_mention, thread_id=thread_id
        )

    await get_db().proxies.transfer_usage(old_proxy.id, new_proxy.id)

    autoproxy = await get_db().user_settings.get_autoproxy_preference(old_proxy.owner, guild)
    if autoproxy:
        await get_db().user_settings.set_autoproxy_preference(old_proxy.owner, replace(autoproxy, last_used_proxy=new_proxy.id))

    await get_db().guilds.link_message(MessageLink(
        MessageDat(
            m.id, context.channel.id, context.platform
        ),
        new_proxy.id,
        message_link.platform_user
    ))

    logging_channel_id = guild_preferences.logging_channel
    if logging_channel_id != 0 and (logging_channel := await context.get_channel(logging_channel_id)):
        embed = Embed(
            f"Message Proxy Change",
            str(
                DelimitedString("\n") +
                f"**Previous Proxy**: {old_proxy.effective_name(
                    await get_db().tags.fetch_bulk(await get_db().relationships.get_relationships(old_proxy.id))
                )}" +
                f"**New Proxy**: {name}" +
                f"**Owner**: <@{message_link.platform_user}> (`{message_link.platform_user}`)" +
                f"**Channel**: {context.channel.mention} (`{context.channel.id}`)" +
                f"**New Message Link**: [jump]({await m.message.mention()})"
            ),
            thumbnail_url=new_proxy.effective_avatar
        )
        await logging_channel.send("", embeds=[embed])


async def edit_proxy_message(old_message: Context, new_message_contents: str, message_link: MessageLink, permissions: GuildPermissions, owner: UserID):
    webhook = await get_webhook(old_message)
    if not webhook:
        return
    if (channel := await old_message.get_channel(old_message.message.channel_id)) is None:
        return

    guild = GuildDat(channel.guild_id, old_message.platform)

    server_preferences = await get_db().guilds.get_guild_preferences(guild)
    contents, embeds = await modify_message(owner, server_preferences, permissions, new_message_contents)

    await webhook.edit(
        old_message,
        contents,
        embeds
    )

    logging_channel_id = server_preferences.logging_channel
    if (
            logging_channel_id and
            (logging_channel := await old_message.get_channel(logging_channel_id)) and
            (proxy := await get_db().proxies.get(message_link.proxy_id))
    ):
        embed = Embed(
            f"Message Edit",
            str(
                DelimitedString("\n") +
                f"**Proxy**: {proxy.effective_name(
                    await get_db().tags.fetch_bulk(await get_db().relationships.get_relationships(proxy.id))
                )}" +
                f"**Owner**: <@{message_link.platform_user}> (`{message_link.platform_user}`)" +
                f"**Channel**: <#{old_message.channel.id}> (`{old_message.channel.id}`)" +
                f"**Message Link**: [jump]({await old_message.message.mention()})" +
                f"**Old Message**:\n{quote(old_message.content)}" +
                f"**New Message**:\n{quote(new_message_contents)}"
            ),
            thumbnail_url=proxy.effective_avatar
        )
        await logging_channel.send("", embeds=[embed])
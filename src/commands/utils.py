from datetime import datetime, timezone
from typing import Callable

from .generic import get_command_invocation, EarlyExitException
from ..backend.database.user_setting import UserPreference
from ..backend.models import FullProxy, ProxyTag, ID
from ..backend.template_utils import Template, TextPart
from ..backend.utils import format_date, quote, list_to_dict, DelimitedString
from ..interaction import Interactions, Interaction
from ..service import Context, Embed, ReactionActionEvent
from ..service.common import Permissions


def sectionize[T](full: list[T], each: Callable[[T], str], preface: str | None = None, limit = 5, max_chars = 4096) -> list[str]:
    pages: list[str] = []
    this_page = DelimitedString("\n", preface)
    run = 0
    for element in full:
        this_section = each(element)

        if len(str(this_page)) + len(this_section) > max_chars or run == limit:
            pages.append(str(this_page))
            this_page = DelimitedString("\n", preface, this_section)
            if len(str(this_page)) > max_chars:
                this_page = DelimitedString("\n", str(this_page)[:max_chars - 4] + "...")
            run = 0
        else:
            this_page += this_section
            run += 1

    pages.append(str(this_page))
    return pages


def get_tag_text(tag: ProxyTag, members_count: int, preferences: UserPreference, detailed = False, show_members = True) -> str:
    out = DelimitedString("\n", f"**{tag.name}** (`{tag.id}`)")

    if tag.tag:
        out += f"- Marker: `{tag.tag}`"
    if preferences.public_metadata or detailed:
        out += f"- Creation Date: {format_date(datetime.fromtimestamp(tag.creation_date))}"
    if (preferences.public_description or detailed) and tag.description:
        out += f"- Description:\n{quote(tag.description)}"
    if (preferences.public_proxy_tags or detailed) and show_members:
        out += f"- Members: {members_count}"

    return str(out)


def get_proxy_text(proxy: FullProxy, tags: list[ProxyTag], preferences: UserPreference, detailed = False, display_tags = True) -> str:
    out = DelimitedString("\n", f"**{proxy.name}**{(' (aka *' + proxy.nickname + '*)') if proxy.nickname else ''} (`{proxy.id}`)")

    if (effective_name := proxy.effective_name(tags)) != proxy.name:
        out += f"-# effectively **{effective_name}**"

    if (preferences.public_proxy_tags or detailed) and display_tags:
        out += f"- Tags: *{'*, *'.join(tag.name for tag in tags) if tags else 'N/A'}*"
    if preferences.public_trigger or detailed:
        out += f"- Triggers: {', '.join(f'`{trigger}`' for trigger in proxy.triggers) if proxy.triggers and any(bool(t) for t in proxy.triggers) else '*N/A*'}"

    out += f"- Avatar: [source]({proxy.avatar_url})"

    if preferences.public_pronouns or detailed:
        if proxy.pronouns:
            out += f"- Pronouns: {proxy.pronouns}"

    if preferences.public_forms or detailed:
        if proxy.forms:
            out += "- Forms:"
            for form_name, form_url in proxy.forms.items():
                out += f"    - {form_name}: [avatar]({form_url}){' (current)' if proxy.current_form == form_name else ''}"

    if preferences.public_metadata or detailed:
        out += f"- Messages Send: {proxy.times_used}"
        out += f"- Creation Date: {format_date(datetime.fromtimestamp(proxy.creation_date))}"
    if preferences.public_description or detailed:
        if proxy.description:
            out += f"- Description:\n{quote(proxy.description)}"

    return str(out)


async def paged_tag_list(
        context: Context,
        tags: list[ProxyTag],
        backward_relationships: dict[ID, list[ID]],
        preferences: UserPreference,
        title: str,
        page: int,
        detailed: bool,
        additional_embeds: list[Embed] | None = None,
        show_members: bool = True
):
    additional_embeds = additional_embeds or []

    if not tags:
        await context.reply("", [Embed(
            f"{title} (0 total)",
            f"It's as empty as a desert out here...\n\nTry running `{get_command_invocation('tag register', context.platform)}` to get started!"
        )] + additional_embeds)
        return

    if not (preferences.public_list or detailed):
        await context.reply("", [Embed(
            f"{title} (? total)",
            "This tag list cannot be viewed."
        )] + additional_embeds)
        return

    pages = sectionize(
        tags,
        lambda tag: get_tag_text(tag, len(backward_relationships.get(tag.id, [])), preferences, detailed, show_members)
    )

    await paged(
        context,
        f"{title} ({len(tags)} total)",
        pages,
        page,
        additional_embeds
    )


async def cannot_view_proxy_list(context: Context, title: str, additional_embeds: list[Embed] | None = None):
    await context.reply("", [Embed(
        f"{title} (? total)",
        "This proxy list cannot be viewed."
    )] + (additional_embeds or []))


async def paged_proxy_list(
        context: Context,
        proxies: list[FullProxy],
        tags: list[ProxyTag],
        relationships: dict[ID, list[ID]],
        preferences: UserPreference,
        title: str,
        page: int,
        detailed: bool,
        additional_embeds: list[Embed] | None = None,
        show_tags: bool = True
):
    additional_embeds = additional_embeds or []

    if not proxies:
        await context.reply("", [Embed(
            f"{title} (0 total)",
            f"It's as empty as a desert out here...\n\nTry running `{get_command_invocation('register', context.platform)}` to get started!"
        )] + additional_embeds)
        return

    if not (preferences.public_list or detailed):
        await cannot_view_proxy_list(context, title, additional_embeds)
        return

    proxies_dict = list_to_dict(proxies, lambda p: p.id)
    tags_dict = list_to_dict(tags, lambda p: p.id)

    pages: list[str] = []
    if (preferences.public_proxy_tags or detailed) and show_tags:
        all_tags: set[ID] = set()
        for proxy in proxies:
            for tag_id in relationships.get(proxy.id, []):
                all_tags.add(tag_id)
        for tag_id in sorted(all_tags):
            tag_proxies = [proxy for proxy, tags in relationships.items() if tag_id in tags]
            tag = tags_dict[tag_id]

            page_fore = f"**Tag**: {tag.name}"

            if tag.description:
                page_fore += "\n"
                page_fore += quote(tag.description)

            pages.extend(sectionize(
                tag_proxies,
                lambda proxy_id: get_proxy_text(proxies_dict[proxy_id], [
                    tags_dict[tag_id] for tag_id in relationships[proxy_id]
                ], preferences, detailed, False),
                page_fore + "\n"
            ))

    tag_proxies = [proxy.id for proxy in proxies if not relationships.get(proxy.id, [])]

    pages.extend(sectionize(
        tag_proxies,
        lambda proxy_id: get_proxy_text(proxies_dict[proxy_id], [], preferences, detailed, False)
    ))

    await paged(
        context,
        f"{title} ({len(proxies)} total)",
        pages,
        page,
        additional_embeds
    )


LEFT, RIGHT = "⬅️", "➡️"

async def paged(context: Context, title: str, pages: list[str], start_page: int, additional_embeds: list[Embed] | None = None):
    author = context.author.id

    async def get_page(p: int) -> Embed | None:
        if not 0 <= p < len(pages):
            await context.reply(f"Error: page {p + 1} is out of range 1~{len(pages)}")
            return None

        description = f"Page {p + 1} / {len(pages)}\n\n" + pages[p]
        return Embed(
            title,
            description
        )

    if embed := await get_page(start_page):
        page = start_page

        reply_ctx = await context.reply("", [embed] + (additional_embeds or []))
        message = reply_ctx.message

        async def callback(event: ReactionActionEvent) -> bool:
            nonlocal page

            if event.emoji in (LEFT, RIGHT):
                if event.emoji == LEFT:
                    await message.remove_reaction(LEFT, author)
                    if page == len(pages) - 1:
                        await message.add_reaction(RIGHT)
                    if page == 1:
                        await message.remove_reaction(LEFT)
                    page -= 1
                else:
                    await message.remove_reaction(RIGHT, author)
                    if page == 0:
                        await message.remove_reaction(RIGHT)
                        await message.add_reaction(LEFT)
                        await message.add_reaction(RIGHT)
                    if page == len(pages) - 2:
                        await message.remove_reaction(RIGHT)
                    page += 1
                page = max(min(page, len(pages) - 1), 0)

                next_page = await get_page(page)
                if next_page is None:
                    return False

                await message.edit("", embeds=[next_page] + (additional_embeds or []))

            return False

        Interactions.instance.add_interaction(
            reply_ctx,
            Interaction(author, callback)
        )

        if len(pages) != 1:
            if page != 0:
                await message.add_reaction(LEFT)
            if page != len(pages) - 1:
                await message.add_reaction(RIGHT)


def example_trigger_text(trigger: Template) -> str:
    res = ""
    for part in trigger.parts:
        if isinstance(part, TextPart):
            res += part.content
        else:
            res += "hello"
    return res


async def require_permissions(context: Context, predicate: Callable[[Permissions], bool]):
    member = await context.get_member(context.author.id)
    channel = await context.get_this_channel()
    if not channel or not member:
        raise EarlyExitException()

    permissions = await channel.permissions_for(member)
    if not predicate(permissions):
        await context.reply(f"Error: you do not have the required permissions to use this command!")
        raise EarlyExitException()

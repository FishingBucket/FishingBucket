from dataclasses import dataclass

from ..backend.database.database import get_db
from ..backend.database.permission import GuildPermissions
from ..backend.database.user import UserID
from ..backend.database.user_setting import AutoproxyPreference, AutoproxyType
from ..backend.models import Proxy
from ..backend.template_utils import Template
from ..backend.utils import normalize_emojis, DelimitedString


@dataclass(slots=True)
class MatchResult:
    value: str | None

    def matched(self) -> bool:
        return self.value is not None

    def match(self) -> str:
        if self.value is None:
            raise ValueError()
        return self.value


@dataclass(slots=True)
class ProxiedMessage:
    proxy: Proxy
    message: str


def text_matches_trigger(text: str, triggers: list[str]) -> MatchResult:
    for trigger in triggers:
        if trigger:
            trigger_norm = normalize_emojis(trigger)
            text_norm = normalize_emojis(text)
            res = Template.from_string(trigger_norm).match(text_norm)
            if res.match:
                return MatchResult(res.content)
    return MatchResult(None)


def get_proxy_from_text(text: str, user_proxies: list[Proxy]) -> ProxiedMessage | None:
    for proxy in user_proxies:
        if proxy.triggers:
            if (res := text_matches_trigger(text, proxy.triggers)).matched():
                return ProxiedMessage(proxy, res.match())
    return None


async def get_first_spotlight_proxies(uid: UserID) -> Proxy | None:
    user_settings = await get_db().user_settings.get_user_preference(uid)
    spotlights = user_settings.spotlight
    if spotlights:
        return await get_db().proxies.get(spotlights[0])

    return None


async def get_proxied_messages(
        message: str,
        user_id: UserID,
        permissions: GuildPermissions,
        autoproxy_preferences: AutoproxyPreference | None
) -> list[ProxiedMessage]:
    autoproxy_proxy = None
    user_proxies = await get_db().proxies.from_user_with_triggers(user_id)

    if autoproxy_preferences and not autoproxy_preferences.do_expire_now():
        if autoproxy_preferences.type == AutoproxyType.SPOTLIGHT:
            autoproxy_proxy = await get_first_spotlight_proxies(user_id)
        else:
            prox_id = autoproxy_preferences.set_proxy if autoproxy_preferences.set_proxy is not None else autoproxy_preferences.last_used_proxy
            if prox_id is not None:
                autoproxy_proxy = await get_db().proxies.get(prox_id)

    if GuildPermissions.MULTIPROXY in permissions:
        res: list[ProxiedMessage] = []
        rolling = DelimitedString("\n")
        last_proxied: ProxiedMessage | None = None
        for line in message.split("\n"):
            rolling += line
            proxied = extract_message(str(rolling), user_proxies, autoproxy_proxy)
            this_line = extract_message(line, user_proxies, autoproxy_proxy)
            if last_proxied is not None:
                r"""
                
                STATE TRANSITION MODEL (100% human formatting)
                
                            Case A
                +-------------------------+ \
                | last_proxied : Proxy A  |  /
                +-------------------------+  > proxied : Proxy A
                | this_line    : Proxy B  |  \
                +-------------------------+ /
                    This means that Proxy A likely used a prefix-only trigger.
                    Do transition
                
                            Case B
                +-------------------------+ \
                | last_proxied : Proxy A  |  /
                +-------------------------+  > proxied : None
                | this_line    : Proxy B  |  \
                +-------------------------+ /
                    Do transition
                
                            Case C
                +-------------------------+ \
                | last_proxied : Proxy A  |  /
                +-------------------------+  > proxied : Proxy A
                | this_line    : None     |  \
                +-------------------------+ /
                    This means this line is a continuation line.
                    Do not transition
                
                            Case D
                +-------------------------+ \
                | last_proxied : Proxy A  |  /
                +-------------------------+  > proxied : Proxy A
                | this_line    : Proxy A  |  \
                +-------------------------+ /
                    Do not transition
                
                """
                if (
                    proxied and last_proxied.proxy is proxied.proxy and this_line and this_line.proxy != proxied.proxy # A
                    or proxied is None and this_line and last_proxied.proxy is not this_line.proxy # B
                ):
                    res.append(last_proxied)
                    rolling = DelimitedString("\n", line)
                    last_proxied = this_line
                else:
                    last_proxied = proxied
            else:
                last_proxied = proxied

        if last_proxied:
            res.append(last_proxied)
        return res
    else:
        proxied = extract_message(message, user_proxies, autoproxy_proxy)
        if proxied:
            return [proxied]
        return []


def extract_message(
        message: str,
        user_proxies: list[Proxy],
        autoproxy_proxy: Proxy | None
) -> ProxiedMessage | None:
    if proxied_message := get_proxy_from_text(message, user_proxies):
        return proxied_message
    else:
        if autoproxy_proxy:
            if message.startswith("\\") and not message.startswith("\\\\"):
                return None
            return ProxiedMessage(autoproxy_proxy, message)
    return None


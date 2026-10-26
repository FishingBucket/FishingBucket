import asyncio
import random
from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Callable, Coroutine, Any, Awaitable

import discord
import fluxer
from fluxer import gateway as fluxer_gateway

from .common import Bot as BotT
from .discord import Bot as DiscordBot
from .fluxer import Bot as FluxerBot
from ..backend.logging import start_log
from ..backend.models import Platform
from ..backend.template_utils import Template
from ..context import config, context

type Coro = Callable[..., Coroutine[Any, Any, Any]]

print, error = start_log("server")

class Server[Bot = fluxer.Bot | discord.Bot](ABC):
    bot: Bot
    platform: Platform
    ready: bool = False

    async def tip_loop(self, platform: str, callback: Callable[[str], Awaitable[None]]):
        tips = context().data_reader["tips.json"]
        refresh_timer = 5 * 60

        current_bucket = tips[:]
        random.shuffle(current_bucket)
        while True:
            if self.ready:
                tip = current_bucket.pop(0)
                parsed = Template.from_string(tip).compute({
                    "prefix": config().fluxer.prefixes[0],
                    "config": config(),
                    "platform": platform,
                    "name": config().name
                }, "")

                await callback(parsed)

                await asyncio.sleep(refresh_timer)
            else:
                await asyncio.sleep(10)

            if len(current_bucket) == 0:
                current_bucket = tips[:]
                random.shuffle(current_bucket)

    @abstractmethod
    async def start(self): pass

    @abstractmethod
    async def close(self): pass

    @abstractmethod
    def event(self, function: Coro): pass

    @abstractmethod
    def clear_events(self): pass

    @abstractmethod
    def get_bot(self) -> BotT: pass


class Fluxer(Server[fluxer.Bot]):
    platform = Platform.Fluxer
    bot: fluxer.Bot

    async def tip_loop_inner(self, parsed: str):
        await self.bot._gateway._send(fluxer_gateway.GatewayPayload(
            op=fluxer_gateway.GatewayOpcode.PRESENCE_UPDATE,
            d={
                "status": "online",
                "custom_status": {
                    "text": parsed,
                    "emoji_name": "",
                    "emoji_id": ""
                },
                "since": None,
                "afk": False
            }
        ))

    def __init__(self):
        self.events: list[Coro] = []
        self.tip_loop_task: asyncio.Task | None = None

    async def start(self):
        self.bot = fluxer.Bot(intents=fluxer.Intents.default(), api_url=config().fluxer.api_url.unicode_string())
        for event in self.events:
            self.bot.event(event)
        if config().use_extras and (self.tip_loop_task is None or self.tip_loop_task.done()):
            self.tip_loop_task = asyncio.create_task(self.tip_loop("Fluxer", self.tip_loop_inner))

        print("Start Fluxer bot")
        await self.bot.start(config().fluxer.token)


    async def close(self):
        print("End Fluxer bot")
        await self.bot.close()

        if self.tip_loop_task is not None and not self.tip_loop_task.done():
            self.tip_loop_task.cancel()

            with suppress(asyncio.CancelledError):
                await self.tip_loop_task

            self.tip_loop_task = None

        print("Fluxer bot finished")


    def event(self, function: Coro):
        self.events.append(function)

    def clear_events(self):
        self.bot._event_handlers.clear()

    def get_bot(self) -> FluxerBot:
        return FluxerBot(self.bot, self.bot)


class Discord(Server[discord.Bot]):
    platform = Platform.Discord
    bot: discord.Bot

    async def tip_loop_inner(self, parsed: str):
        await self.bot.change_presence(activity=discord.CustomActivity(parsed), status=discord.Status.online)

    def __init__(self):
        self.events: list[Coro] = []
        self.tip_loop_task: asyncio.Task | None = None

    async def start(self):
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = discord.Bot(intents=intents)
        for event in self.events:
            self.bot.event(event)

        if config().use_extras and (self.tip_loop_task is None or self.tip_loop_task.done()):
            self.tip_loop_task = asyncio.create_task(self.tip_loop("Discord", self.tip_loop_inner))

        print("Start Discord bot")
        await self.bot.start(config().discord.token)


    async def close(self):
        print("End Discord bot")
        await self.bot.close()

        if self.tip_loop_task is not None and not self.tip_loop_task.done():
            self.tip_loop_task.cancel()

            with suppress(asyncio.CancelledError):
                await self.tip_loop_task

            self.tip_loop_task = None

        print("Discord bot finished")

    def event(self, function: Coro):
        self.events.append(function)

    def clear_events(self):
        self.bot._event_handlers.clear()

    def get_bot(self) -> DiscordBot:
        return DiscordBot(self.bot, self.bot)


ALL_SERVERS: list[type[Server]] = [Fluxer, Discord]

SERVER_INSTANCES: list[Server] = []
PLATFORM_TO_SERVER: dict[Platform, Server] = {}

def setup_instances() -> list[Server]:
    for server in ALL_SERVERS:
        if config().cfg(server.platform):
            s = server()
            SERVER_INSTANCES.append(s)
            PLATFORM_TO_SERVER[s.platform] = s

    return SERVER_INSTANCES

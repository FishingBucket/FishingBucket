import re
import shutil
import json
import asyncio
import aiohttp
import base64
import typer

from math import floor, ceil
from pathlib import Path
from typing import Callable, Any
from getpass import getpass
from urllib.parse import urlparse

import download_emojis


if not Path("./src").exists():
    print("Please run this Python script with CWD set to the repository root!")
    exit(1)


MAX_COLUMNS = shutil.get_terminal_size().columns
H1 = "=" * MAX_COLUMNS

FLUXER_BOT_TOKEN_RE = re.compile(r"(\d+)\.[a-zA-Z0-9_-]{43}")
DISCORD_BOT_TOKEN_RE = re.compile(r"([a-zA-Z0-9_-]+?)\.([a-zA-Z0-9_-]+?)\.([a-zA-Z0-9_-]+?)")
FLUXER_CLIENT_SECRET_RE = re.compile(r"[a-zA-Z0-9_-]{43}")
DISCORD_CLIENT_SECRET_RE = re.compile(r"[a-zA-Z0-9_-]{32}")

YN_VALIDATE = ((lambda s: bool(s) and s.lower()[0] in "yn"), "Please enter a yes or a no!")

def center(text: str) -> str:
    remaining_spaces = MAX_COLUMNS - len(text)
    return " " * floor(remaining_spaces / 2) + text + " " * ceil(remaining_spaces / 2)


def path_is_valid(attempt: str) -> bool:
    try:
        Path(attempt).resolve()
        return True
    except (OSError, RuntimeError):
        return False

def valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except AttributeError:
        return False

previous_fluxer_instance: dict = {}

def is_fluxer_instance(url: str) -> bool:
    tries = [url.rstrip("/") + "/.well-known/fluxer", url.rstrip("/") + "/api/.well-known/fluxer"]

    async def get_information() -> bool:
        global previous_fluxer_instance

        async with aiohttp.ClientSession() as session:
            for attempt in tries:
                try:
                    async with session.get(attempt) as response:
                        previous_fluxer_instance = await response.json()
                        return True
                except aiohttp.ClientError, json.JSONDecodeError:
                    continue
            return False

    return asyncio.run(get_information())

def get_fluxer_instance(url: str) -> dict:
    if not previous_fluxer_instance:
        is_fluxer_instance(url)

    return previous_fluxer_instance

def is_int(text: str) -> bool:
    try:
        int(text)
        return True
    except ValueError:
        return False


def prompt(
        pre: str,
        validate: tuple[Callable[[str], bool], str] | None = None,
        *,
        indent: int = 0,
        password: bool = False,
        confirmation_text: Callable[[str], str | None] | None = None,
        newline: bool = True
) -> str:
    indents = " " * (indent * 2)
    print(indents + " * " + pre)
    while True:
        if password:
            res = getpass(indents + " * > ")
        else:
            res = input(indents + " * > ")

        if validate:
            if not validate[0](res):
                print(indents + "   * Invalid input. " + validate[1])
                continue

        if confirmation_text:
            confirm_text = confirmation_text(res)
            if confirm_text:
                confirm = prompt(
                    "Are you sure [y/n]? " + confirm_text,
                    YN_VALIDATE,
                    indent=indent + 1,
                    newline=False
                )
                if confirm.lower()[0] == "n":
                    continue

        if newline:
            print()

        return res


def main():
    print()
    
    print(center("FishingBucket self-host wizard in a snake"))
    print(H1)
    print()
    
    make_paths: list[Path] = []
    
    config_path = Path(prompt(
        "Your bot needs a place to put the configuration file in. Give it a location somewhere permanent.",
        (path_is_valid, "Make sure it is a valid path! Doesn't have to exist!"),
        confirmation_text=lambda s: (
            "This will overwrite the previous config!"
            if Path(s).exists() else None
        )
    ))
    make_paths.append(config_path.parent)
    
    bot_name = prompt(
        "Your bot needs a name. Give it a name.",
        (lambda s: 1 < len(s) < 32, "Make sure the name is within 1..=32 characters!")
    )
    
    database_path = prompt(
        f"{bot_name} needs a place to store its database. Give it a location somewhere permanent.",
        (path_is_valid, "Make sure it is a valid path! Doesn't have to exist!"),
        confirmation_text=lambda s: (
            "This will reuse the previous database!"
            if Path(s).exists() else None
        )
    )
    
    logs_directory = Path(prompt(
        f"{bot_name} needs a place to store its logs. Give it a location somewhere temporary.",
        (lambda s: path_is_valid(s) and (Path(s).is_dir() if Path(s).exists() else True), "Make sure it is a valid directory path! Doesn't have to exist!")
    ))
    make_paths.append(logs_directory)
    
    webhook_name = prompt(
        f"{bot_name} needs a name for the thousands of webhooks it will create. Give it something descriptive.",
        (lambda s: 1 < len(s) < 32, "Make sure the name is within 1..=32 characters!")
    )
    
    instance = prompt(
        f"{bot_name} needs to run on a Fluxer instance. Give it its URL. Defaults to https://fluxer.app.",
        (lambda s: not s or is_fluxer_instance(s), "Make sure the provided URL points to a Fluxer instance!")
    )
    
    instance_information = get_fluxer_instance(instance or "https://fluxer.app")
    api_url = instance_information["endpoints"]["api_public"].rstrip("/") + "/v" + str(instance_information["api_code_version"])
    webapp_url = instance_information["endpoints"]["webapp"]
    invite_url = instance_information["endpoints"]["invite"]
    
    print(f" Information received. Found API URL at {api_url} and webapp URL at {webapp_url}.")
    print()
    
    token = FLUXER_BOT_TOKEN_RE.fullmatch(prompt(
        f"{bot_name} needs a token. Give it a token to log in with.",
        (lambda s: bool(FLUXER_BOT_TOKEN_RE.fullmatch(s)), "Make sure you are providing a valid Fluxer token!"),
        password=True
    ))
    assert token is not None
    
    client_id = int(token.group(1))
    print(f" Information received. Found client ID {client_id}.")
    print()
    
    guild_invite = prompt(
        f"(Optional) {bot_name} wants a support community. Give it its invite link, if any.",
        (lambda s: not s or s.startswith(invite_url), "Make sure you are providing a valid invite URL for the instance!")
    )
    
    guild_id = 0
    
    if guild_invite:
        guild_id = int(prompt(
            f"{bot_name} needs your support community's ID. Give it the community ID.",
            (lambda s: is_int(s) and int(s) > 0, "Make sure you are providing a valid community ID!"),
        ))
    
    
    output_dict: dict[str, Any] = {
        "$schema": str(Path("./config.schema.json").absolute()),
        "name": bot_name,
        "database_file": str(Path(database_path).absolute()),
        "data_path": str(Path("./data").absolute()),
        "webhook": webhook_name,
        "log_directory": str(Path(logs_directory).absolute()),
        "log_time_format": "%Y-%m-%d_%H-%M-%S",
        "fluxer": {
            "token": token.group(0),
            "guild_invite": guild_invite,
            "guild_id": guild_id,
            "bot_invite": f"{webapp_url}/oauth2/authorize?client_id={client_id}&scope=bot&permissions=137976212560",
            "client_id": client_id,
            "api_url": api_url,
            "prefixes": [
                "fish!",
                f"<@{client_id}>"
            ]
        }
    }
    
    do_discord = prompt(
        f"Do you want {bot_name} to work on Discord also [y/n]?",
        YN_VALIDATE
    )
    
    discord_client_id = 0
    if do_discord.lower()[0] == "y":
        discord_token = DISCORD_BOT_TOKEN_RE.fullmatch(prompt(
            f"{bot_name} needs a token. Give it a token to log in with.",
            (lambda s: bool(DISCORD_BOT_TOKEN_RE.fullmatch(s)), "Make sure you are providing a valid Discord token!"),
            password=True
        ))
        assert discord_token is not None
        discord_token_client_id_part = discord_token.group(1)
        discord_client_id = int(base64.b64decode(discord_token_client_id_part + "=" * (len(discord_token_client_id_part) % 4)).decode())
        print(f" Information received. Found client ID {discord_client_id}.")
        print()
    
        discord_guild_invite = prompt(
            f"(Optional) {bot_name} wants a support server. Give it its invite link, if any.",
            (lambda s: not s or s.startswith("https://discord.gg"), "Make sure you are providing a valid https://discord.gg invite!")
        )
    
        discord_guild_id = 0
    
        if discord_guild_invite:
            discord_guild_id = int(prompt(
                f"{bot_name} needs your support server's ID. Give it the server ID.",
                (lambda s: is_int(s) and int(s) > 0, "Make sure you are providing a valid server ID!"),
            ))
    
        output_dict["discord"] = {
            "token": discord_token.group(0),
            "guild_invite": discord_guild_invite,
            "guild_id": discord_guild_id,
            "bot_invite": f"https://discord.com/oauth2/authorize?client_id={discord_client_id}&permissions=413122554944&integration_type=0&scope=bot",
            "client_id": discord_client_id,
            "api_url": "https://discord.com/api/v10",
            "prefixes": [
                "fish!",
                f"<@{discord_client_id}>"
            ]
        }
    
    
    do_extra = prompt(
        f"Do you want {bot_name} to use extra features like donation link and API [y/n]?",
        YN_VALIDATE
    )
    
    if do_extra.lower()[0] == "y":
        output_dict["use_extras"] = True
    
        donation_link = prompt(
            f"(Optional) {bot_name} wants a donation link to financially support you. Give it the URL, if any.",
            (lambda s: not s or valid_url(s), "Make sure you are providing a valid URL!"),
        )
        output_dict["donation"] = donation_link or None
    
        website = prompt(
            f"(Optional) {bot_name} wants the website at which the dashboard exists. Give it the URL, if any.",
            (lambda s: not s or valid_url(s), "Make sure you are providing a valid URL!"),
        )
        if not website:
            output_dict["website"] = None
        else:
            root = website.rstrip("/")
            output_dict["website"] = {
                "dashboard": root + "/dashboard",
                "home": root,
                "terms": root + "/terms",
                "privacy": root + "/privacy",
                "contact": root + "/contact",
            }
    
        do_api = "y"
        if not website:
            do_api = prompt(
                f"Do you want {bot_name} to enable an API server [y/n]?",
                YN_VALIDATE
            )
    
        if do_api.lower()[0] == "y":
            host = prompt(
                "(Optional) Provide the host IP to start the API server on. Uses localhost if not provided.",
            ) or "localhost"
            port = int(prompt(
                "Provide the port to start the API server on.",
                (lambda s: is_int(s) and 0 < int(s) < 65536, "Make sure you are providing a valid port!"),
                confirmation_text=lambda s: f"The API server will start on http://{host}:{s}."
            ))
    
            api_database_path = Path(prompt(
                "Provide the location to store API information. Give it a location somewhere permanent.",
                (path_is_valid, "Make sure it is a valid path! Doesn't have to exist!"),
                confirmation_text=lambda s: (
                    "This will reuse the previous database!"
                    if Path(s).exists() else None
                )
            ))
            make_paths.append(api_database_path.parent)
    
            client_secret = prompt(
                "Provide the Fluxer bot's client secret.",
                (lambda s: bool(FLUXER_CLIENT_SECRET_RE.fullmatch(s)), "Make sure you provide a valid Fluxer application client secret!"),
                password=True
            )
            api_server: dict[str, Any] = {
                "enabled": True,
                "domain": host,
                "port": port,
                "database": str(Path(api_database_path).absolute()),
                "fluxer": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                }
            }
            if "discord" in output_dict:
                discord_client_secret = prompt(
                    "Provide the Discord bot's client secret.",
                    (lambda s: bool(DISCORD_CLIENT_SECRET_RE.fullmatch(s)), "Make sure you provide a valid Discord client secret!"),
                    password=True
                )
                api_server["discord"] = {
                    "client_id": discord_client_id,
                    "client_secret": discord_client_secret,
                }
    
            output_dict["api_server"] = api_server
    
        else:
            output_dict["api_server"] = None
    
    
    print(H1)
    print()
    print(center("Creating directories..."))
    for path in make_paths:
        try:
            print(center(f"Making {str(path.absolute())}..."))
            path.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            pass
    
    print(center("Done! Writing configuration file..."))
    
    with open(config_path, "w+") as file:
        file.write(json.dumps(output_dict, indent=2))
    
    print(center("Configuration writing done!"))
    
    if output_dict.get("api_server"):
        print()
        do_caddyfile = prompt(
            "You have API server enabled. Do you want a quickstart Caddyfile [y/n]?",
            YN_VALIDATE
        )
        if do_caddyfile.lower()[0] == "y":
            api_server_url = prompt(
                "Enter the URL you want to bind to the API server.",
                (valid_url, "Make sure you are providing a valid URL!"),
            )
    
            do_cors = False
            if output_dict.get("website"):
                do_cors = prompt(
                    f"Do you want to add CORS for the frontend, {output_dict['website']['home']} [y/n]?",
                    YN_VALIDATE
                ).lower()[0] == "y"
    
            cors = ""
            if do_cors:
                cors = (
                    "  @cors_preflight {\n"
                    "    method OPTIONS\n"
                    "    header Origin *\n"
                    "  }\n"
                    "  \n"
                    "  respond @cors_preflight 204\n"
                    "  \n"
                    "  handle @cors_preflight {\n"
                    "    header {"
                   f"      Access-Control-Allow-Origin \"{output_dict['website']['home']}\"\n"
                    "      Access-Control-Allow-Methods \"GET, POST, OPTIONS\"\n"
                    "      Access-Control-Allow-Headers \"Content-Type, Authorization, X-Requested-With\"\n"
                    "      Access-Control-Max-Age \"3600\"\n"
                    "    }\n"
                    "  }\n"
                    "  \n"
                    "  header {\n"
                   f"    Access-Control-Allow-Origin \"{output_dict['website']['home']}\"\n"
                    "    Access-Control-Allow-Credentials \"true\"\n"
                    "    Access-Control-Expose-Headers \"Content-Length, X-Request-ID\"\n"
                    "  }\n\n"
                )
    
            caddy = (
                ""
               f"{api_server_url} {{\n"
               f"{cors}"
               f"  reverse_proxy {output_dict['api_server']['domain']}:{output_dict['api_server']['port']} {{\n"
                "    header_up Host {host}\n"
                "    header_up X-Real-IP {remote}\n"
                "    header_up X-Forwarded-For {remote}\n"
                "    header_up X-Forwarded-Proto {scheme}\n"
                "    header_up Origin {http.request.header.Origin}\n"
                "  }\n"
                "}"
            )
            caddy_path = Path(prompt(
                "The Caddyfile is ready. Give it a location somewhere permanent.",
                (path_is_valid, "Make sure it is a valid path! Doesn't have to exist!"),
                confirmation_text=lambda s: (
                    "This will overwrite the previous Caddyfile!"
                    if Path(s).exists() else None
                )
            ))
            print(H1)
            try:
                print(center(f"Making {str(caddy_path.parent.absolute())}..."))
                caddy_path.parent.mkdir(parents=True, exist_ok=True)
            except FileExistsError:
                pass
            print(center("Done! Writing Caddyfile..."))
            with open(Path(caddy_path).absolute(), "w+") as file:
                file.write(caddy)
            print(center("Caddyfile writing done!"))
    
    print()
    print(H1)
    print()
    
    print(center("Running final scripts..."))
    download_emojis.download_emoji(Path("./data/emojis.json"))
    
    print()
    print(center("This has been FishingBucket self-host wizard in a snake"))
    print()


app = typer.Typer()

@app.command(help="Shows the self-host wizard.")
def wizard():
    main()

@app.command(help="Redownloads and reprocesses external dependencies.")
def redownload():
    download_emojis.download_emoji(Path("./data/emojis.json"))

app()

import random

from ..generic import make_command, Argument, make_command_group, get_commands, get_command_groups, CommandGroup, \
    Command
from ..generic.strategies import OneOf, OptionList, Optional
from ...backend.config import Config

bot_group: CommandGroup


def setup():
    global bot_group

    bot_group = make_command_group(
        "bot_commands",
        "Bot Commands",
        "Commands related to the bot itself."
    )

    bot_group.append(
        make_command(
            "ping",
            "Gets the bot's latency.",
            "Gets the bot's latency.",
            []
        )
    )

    bot_group.append(
        make_command(
            "invite",
            "Invite me to your community!",
            "Invite me to your community, or join the bot's support community!",
            []
        )
    )

    bot_group.append(
        make_command(
            "explain",
            "What do I do?",
            """
            What do I do?
            """,
            []
        )
    )

    bot_group.append(
        make_command(
            {
                "stats": ["botinfo"]
            },
            "Get global statistics about the bot.",
            """
            Get global statistics about the bot.
            If provided, `stat` will return only that specific statistic.
            """,
            [
                Argument(
                    "stat",
                    Optional(
                        OptionList(
                            "stat",
                            [
                                "proxy_uses",
                                "guilds",
                                "total_proxies",
                                "uptime",
                                "cache_efficiency",
                                "command_count",
                                "invocations",
                                "database_version",
                                "version",
                                "system",
                                "framework"
                            ]
                        ),
                        None
                    )
                )
            ]
        )
    )


    if Config.instance.website:
        bot_group.append(
            make_command(
                {
                    "dashboard": [
                        "dash"
                    ]
                },
                "Opens the link to the online dashboard.",
                """
                Opens the link to the online dashboard.
                """,
                []
            )
        )

        bot_group.append(
            make_command(
                {
                    "website": [
                        "site"
                    ]
                },
                "Opens the link to the online website homepage.",
                """
                Opens the link to the online website homepage.
                """,
                []
            )
        )

        bot_group.append(
            make_command(
                {
                    "legal": [
                        "terms",
                        "privacy",
                        "tos"
                    ]
                },
                "Links to the legal pages on the website.",
                """
                Links to the legal pages on the website.
                Contains Terms of Service and Privacy Policy.
                """,
                []
            )
        )

        bot_group.append(
            make_command(
                "contact",
                "Opens the link to the Contact Us page on the website.",
                """
                Opens the link to the Contact Us page on the website.
                """,
                []
            )
        )

    if Config.instance.donation:
        bot_group.append(
            make_command(
                "donate",
                "Opens the link to the donation page.",
                """
                Opens the link to the donation page.
                """,
                []
            )
        )



def setup_help_command():
    bot_group.append(
        make_command(
            {
                "help": ["h", "?", ""]
            },
            "Provides information about this bot or about a command.",
            """
            Provides information about this bot or about a command or command category.
            If a command is provided, it will show the command description, usage, as well as examples.
            If a category is provided, it will then show the commands on that category.
            """,
            [
                Argument(
                    "topic",
                    Optional(
                        str,
                        None
                    ),
                    lambda: random.choice([command.canonical_name for command in get_commands().values()] + [group.canonical_name for group in get_command_groups().values()]),
                )
            ]
        )
    )
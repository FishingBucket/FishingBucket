from ..generic import make_command_group, make_command, Argument
from ..generic.strategies import OneOf, List, Literal, Optional, OptionList
from ...backend.config import Config
from ...service import Channel, Role, User


def setup():
    guild_group = make_command_group(
        "guild_commands",
        "Community Commands",
        f"Commands that changes how {Config.name()} functions in your community."
    )

    guild_group.append(
        make_command(
            {
                "permissions set": [
                    "perms set",
                    "perms =",
                    "allow proxy"
                ]
            },
            "Change permissions within the community.",
            """
            Change permissions within the community.
            You must have the **Manage Community** permission to use this command.
            This will not override previous settings.
            The resolution order is always as follows: community, channel, role, and finally user.
            
            The possible permissions are:
            - Proxying (`proxy`)
            - Use embed blocks (`embed`)
            - Use multiple proxies at once (`multiproxy`)
            - Use dice functionality (`dice`)
            """,
            [
                Argument(
                    "targets",
                    OneOf(
                        List(
                            OneOf(
                                Channel,
                                Role,
                                User,
                                fatal=True
                            ),
                            1,
                            True
                        ),
                        Literal(
                            "community"
                        )
                    )
                ),
                Argument(
                    "allow",
                    OneOf(
                        bool,
                        Literal("default")
                    )
                ),
                Argument(
                    "permissions",
                    List(
                        OptionList(
                            None,
                            [
                                "proxy",
                                "embed",
                                "multiproxy",
                                "dice"
                            ]
                        )
                    )
                )
            ]
        )
    )


    guild_group.append(
        make_command(
            {
                "permissions reset": [
                    "perms reset",
                    "reset allows"
                ]
            },
            "Reset all proxying settings in this community.",
            """
            Reset all proxying settings in this community.
            You must have the **Manage Community** permission to use this command.
            This will allow proxying everywhere in the community and remove all role, channel, and user overrides.
            """,
            []
        )
    )


    guild_group.append(
        make_command(
            {
                "permissions list": [
                    "perms list",
                    "perms l"
                ]
            },
            "See a list of places where proxying is allowed or disallowed.",
            """
            See a list of places where proxying is allowed or disallowed.
            You *do not* need the Manage Community permission to use this command.
            """,
            []
        )
    )


    guild_group.append(
        make_command(
            {
                "log set": [
                    "logging channel"
                ]
            },
            "Sets the channel to log to on each proxy message.",
            """
            Sets the channel to log to on each proxy message.
            You must have the **Manage Community** permission to use this command.
            If no channel is provided, the logging channel will be cleared.
            """,
            [
                Argument(
                    "channel",
                    Optional(
                        Channel,
                        None
                    )
                )
            ]
        )
    )


    guild_group.append(
        make_command(
            "log view",
            "Views the channel that was set as the logging channel in this community.",
            """
            Views the channel that was set as the logging channel in this community.
            You *do not* need the Manage Community permission to use this command.
            """,
            []
        )
    )

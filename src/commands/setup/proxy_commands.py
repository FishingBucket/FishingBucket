import random
import string
from datetime import timedelta

from ..generic import make_command_group, make_command, Argument
from ..generic.strategies import Optional, OneOf, Literal, OptionList
from ..specific import TemplateStrategy, UnknownPageNumber, ProxyStrategy


def random_trigger():
    return random.choice([
        random.choice(string.ascii_letters) + random.choice(string.punctuation) + " " * random.randint(0, 1) + "{}",
        (brackets := random.choice(("()", "[]", "{}", "~~", "^^", "&&", "--", "__", "**", "!!", ";;", "<>")))[0] + "{}" + brackets[1],
        "name: {}",
        "{}-" + random.choice(string.ascii_letters)
    ])


def setup():
    proxy_commands = make_command_group(
        "proxy_commands",
        "Proxy Commands",
        "Commands related to creating, getting, and using proxies."
    )

    proxy_commands.append(
        make_command(
            {
                "register": [
                    "r"
                ]
            },
            "Registers a proxy to be used.",
            """
            Registers a proxy to be used. This will also create your account.
            The trigger is a string that contains `{}` somewhere.
            Proxy avatar can be set by attaching an image to the message.
            """,
            [
                Argument(
                    "name",
                    str,
                    lambda: "\"My Proxy's Name\""
                ),
                Argument(
                    "trigger",
                    TemplateStrategy([
                        "text"
                    ]),
                    random_trigger
                )
            ]
        )
    )

    proxy_commands.append(
        make_command(
            {
                "list": [
                    "l"
                ]
            },
            "Lists your registered proxies.",
            """
            Lists your registered proxies.
            If `page` is provided, it will display the proxies on that page number.
            If `detailed` is provided, it will ignore your privacy preferences and display everything. This is automatically true in DMs.
            As of now, this command will not be able to inspect another user's proxies.
            """,
            [
                Argument(
                    "page",
                    Optional(
                        UnknownPageNumber(),
                        0
                    )
                ),
                Argument(
                    "detailed",
                    Optional(
                        bool,
                        False
                    )
                )
            ]
        )
    )

    proxy_commands.append(
        make_command(
            {
                "find": [
                    "f"
                ]
            },
            "Finds all of your proxies that matches a certain name.",
            """
            Finds all of your proxies that matches a certain name.
            The first result will be chosen if you use the name as an argument to `proxy` type parameters.
            This will also list some issues that might give you an error if the name is used.
            """,
            [
                Argument(
                    "name",
                    str,
                    lambda: random.choice([
                        "\"My Proxy's Name\"",
                        "\"My Proyx's Naem\"",
                        "\"my poxy'sn ame\""
                    ])
                )
            ]
        )
    )

    proxy_commands.append(
        make_command(
            {
                "info": [
                    "i"
                ]
            },
            "Shows you information about a proxy.",
            """
            Shows you information about a proxy that you own.
            If `detailed` is provided, it will ignore your privacy preferences and display everything. This is automatically true in DMs.
            As of now, this command will not be able to inspect another user's proxies.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "detailed",
                    Optional(
                        bool,
                        False
                    )
                )
            ]
        )
    )

    proxy_commands.append(
        make_command(
            {
                "reproxy": [
                    "rp"
                ]
            },
            "Changes the proxy of your last message in this channel.",
            """
            Changes the proxy of your last message in this channel.
            This will delete and resend your previous proxied message in this channel.
            Alternatively, reply to a message to reproxy that message instead.
            """,
            [
                Argument(
                    "new",
                    ProxyStrategy()
                )
            ]
        )
    )

    proxy_commands.append(
        make_command(
            {
                "autoproxy": [
                    "ap", "auto"
                ]
            },
            "Automatically proxies your messages.",
            """
            Automatically proxies your messages.
            Autoproxy set to `true` or `latch` will proxy your messages as your last used proxy.
            Autoproxy set to `latch` will proxy your messages as the first proxy in your spotlight.
            If `target` is a proxy, all messages will be sent as that proxy.
            You can still use proxies normally. Any explicit proxy message will override the autoproxy for that message only.
            If `expiration` is set, then the autoproxy will automatically expire after `expiration` seconds.
            """,
            [
                Argument(
                    "setting",
                    OneOf(
                        OptionList(None, {
                            "latch": ["l"],
                            "spotlight": ["spot", "front"]
                        }, True),
                        bool,
                        ProxyStrategy()
                    )
                ),
                Argument(
                    "mode",
                    Optional(
                        OptionList(
                            None,
                            [
                                "global",
                                "community"
                            ],
                            True
                        ),
                        None
                    )
                ),
                Argument(
                    "expiration",
                    Optional(
                        OneOf(
                            Literal(
                                "never"
                            ),
                            timedelta,
                            fatal=True
                        ),
                        "never"
                    )
                )
            ]
        )
    )

    proxy_commands.append(
        make_command(
            {
                "who": [
                    "showuser"
                ]
            },
            "Shows you information about a proxied message.",
            """
            Shows you information about a proxied message.
            This requires the command to be a reply to a message sent by a proxy.
            Alternatively, react to a proxied message with :question: to do the same thing!
            """,
            []
        )
    )

    proxy_commands.append(
        make_command(
            {
                "delete": [
                    "del"
                ]
            },
            "Deletes a proxied message.",
            """
            Deletes a proxied message.
            This requires the command to be a reply to a message sent by a proxy.
            Alternatively, react to a proxied message with :x: to do the same thing!
            
            If you have the Manage Messages permission, setting the `bypass` argument to true will bypass the proxy ownership check.
            """,
            [
                Argument(
                    "bypass",
                    Optional(
                        bool,
                        False
                    )
                )
            ]
        )
    )

    proxy_commands.append(
        make_command(
            {
                "edit": [
                    "e"
                ]
            },
            "Edits a proxied message.",
            """
            Edits a proxied message.
            If the command was sent as a reply, the replied message is edited. Otherwise it will edit the latest message.
            You must own the proxy to edit the message.
            """,
            [
                Argument(
                    "message",
                    str
                )
            ]
        )
    )

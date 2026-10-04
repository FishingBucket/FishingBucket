import random

from ..generic import make_command_group, make_command, Argument
from ..generic.misc import lorem_ipsum
from ..generic.strategies import URLStrategy, Optional, OptionList, List, StringStrategy, Sequence
from ..specific import ProxyStrategy, TemplateStrategy, ProxyTagStrategy


def setup():
    proxact_group = make_command_group(
        "proxy_action_commands",
        "Proxy Action Commands",
        "Commands that modify proxies."
    )

    proxact_group.append(
        make_command(
            {
                "set avatar": [
                    "avatar",
                    "s avatar"
                ]
            },
            "Updates a proxy's avatar.",
            """
            Updates a proxy's avatar.
            The new avatar could be attached to the message or passed down as a link in the `url` argument.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "url",
                    Optional(
                        URLStrategy(),
                        None
                    )
                )
            ]
        )
    )

    proxact_group.append(
        make_command(
            {
                "set triggers": [
                    "triggers",
                    "trigger",
                    "s triggers",
                    "s trigger",
                    "set trigger"
                ]
            },
            "Updates a proxy's triggers.",
            """
            Updates a proxy's triggers.
            A proxy can have more than one trigger. A trigger must contain `{}` or an expression slot in it.
            If `mode` is set to add, then there must be a trigger.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "mode",
                    OptionList(
                        None,
                        {
                            "set": [
                                "s",
                                "="
                            ],
                            "add": [
                                "a",
                                "+"
                            ],
                            "remove": [
                                "r",
                                "rm",
                                "rem",
                                "-"
                            ]
                        }
                    )
                ),
                Argument(
                    "trigger",
                    Optional(
                        TemplateStrategy([
                            "text"
                        ]),
                        None
                    )
                )
            ]
        )
    )

    proxact_group.append(
        make_command(
            {
                "set name": [
                    "name",
                    "s name"
                ]
            },
            "Updates a proxy's name.",
            """
            Updates a proxy's name.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "new name",
                    str,
                    lambda: "\"My Proxy's Name\""
                )
            ]
        )
    )

    proxact_group.append(
        make_command(
            {
                "set nickname": [
                    "nickname",
                    "nick",
                    "set nick",
                    "s nickname",
                    "s nick"
                ]
            },
            "Updates a proxy's nickname.",
            """
            Updates a proxy's nickname.
            The `new nickname` argument will always be displayed as the name of your proxy after changing it.
            If `new nickname` is not provided, the nickname will instead be cleared
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "new nickname",
                    Optional(
                        str,
                        ""
                    ),
                    lambda: random.choice(["\"My Proxy's Nickname\"", ""])
                )
            ]
        )
    )


    proxact_group.append(
        make_command(
            {
                "set pronouns": [
                    "pronouns",
                    "s pronouns"
                ]
            },
            "Updates a proxy's pronouns.",
            """
            Updates a proxy's pronouns.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "new pronoun",
                    Optional(str, ""),
                    lambda: random.choice([lorem_ipsum("MINI")(), random.choice(["he", "she", "they", "it", "any"]) + "/" + random.choice(["him", "her", "them", "its", "all"]), ""])
                )
            ]
        )
    )


    proxact_group.append(
        make_command(
            {
                "set description": [
                    "description",
                    "desc",
                    "set desc",
                    "s description",
                    "s desc"
                ]
            },
            "Updates a proxy's description.",
            """
            Updates a proxy's description.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "new description",
                    Optional(
                        StringStrategy("MEDIUM"),
                        ""
                    )
                )
            ]
        )
    )

    proxact_group.append(
        make_command(
            {
                "set tags": [
                    "set tag",
                    "tags"
                ]
            },
            "Updates a proxy's tags.",
            """
            Updates a proxy's tags.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "mode",
                    OptionList(
                        None,
                        {
                            "add": ["+"],
                            "remove": ["rem", "rm", "-"]
                        }
                    )
                ),
                Argument(
                    "tags",
                    List(
                        ProxyTagStrategy()
                    )
                )
            ]
        )
    )

    proxact_group.append(
        make_command(
            {
                "set forms": [
                    "forms",
                    "s forms"
                ]
            },
            "Updates a proxy's different forms.",
            """
            Updates a proxy's different forms.
            A proxy form is an avatar that can be quickly reloaded or changed. This command does not update the current form.
            Form avatar can either be a URL or submitted as an attachment.
            If removing a form, then only the form name is taken into account.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "mode",
                    OptionList(
                        None,
                        {
                            "set": [
                                "s",
                                "="
                            ],
                            "add": [
                                "a",
                                "+"
                            ],
                            "remove": [
                                "r",
                                "rm",
                                "rem",
                                "-"
                            ]
                        }
                    )
                ),
                Argument(
                    "form",
                    Optional(
                        Sequence(
                            Argument(
                                "name",
                                StringStrategy("MINI")
                            ),
                            Argument(
                                "avatar",
                                Optional(
                                    URLStrategy(),
                                    None
                                )
                            )
                        ),
                        None
                    )
                )
            ]
        )
    )

    proxact_group.append(
        make_command(
            {
                "set current form": [
                    "set form",
                    "current form",
                    "s form",
                    "s current form"
                ]
            },
            "Sets the current form of the proxy.",
            """
            Sets the current form of the proxy.
            If the form is not provided, the form will be cleared.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                ),
                Argument(
                    "form",
                    Optional(
                        StringStrategy("MINI"),
                        ""
                    )
                )
            ]
        )
    )

    proxact_group.append(
        make_command(
            {
                "remove": [
                    "rem",
                    "rm"
                ]
            },
            "Removes a proxy that you own.",
            """
            Removes a proxy that you own.
            Messages will not be deleted, but you will no longer be able to use or modify this proxy.
            """,
            [
                Argument(
                    "proxy",
                    ProxyStrategy()
                )
            ]
        )
    )

    proxact_group.append(
        make_command(
            "nuke",
            "Deletes every proxy associated with your account.",
            """
            Deletes every proxy and proxy tag associated with your account.
            This does not delete your account fully.
            This action is irreversible! Make sure you really want to do this!
            """,
            []
        )
    )

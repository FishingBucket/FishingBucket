import random

from ..generic import make_command_group, make_command, Argument
from ..generic.strategies import Optional, StringStrategy
from ..specific import UnknownPageNumber, ProxyTagStrategy, TemplateStrategy, PROXY_TAG_OPTIONS


def setup():
    tag_name_example = lambda: random.choice(PROXY_TAG_OPTIONS)

    tag_commands = make_command_group(
        "tag_commands",
        "Tag Commands",
        "Commands related to creating and adjusting tags.",
        {
            "tag": [
                "group",
                "t",
                "g"
            ]
        }
    )

    tag_commands.append(
        make_command(
            {
                "tag register": {
                    "register": [
                        "r",
                        "new",
                        "create"
                    ]
                }
            },
            "Creates a new tag.",
            """
            Creates a new tag. This will also create your account if you do not have one.
            Tags help you group together different proxies.
            """,
            [
                Argument(
                    "name",
                    str,
                    tag_name_example
                ),
                Argument(
                    "description",
                    Optional(
                        StringStrategy("MEDIUM"),
                        ""
                    )
                )
            ]
        )
    )

    tag_commands.append(
        make_command(
            {
                "tag list": {
                    "list": [
                        "l"
                    ]
                }
            },
            "Lists your tags.",
            """
            Lists your tags.
            
            If `page` is provided, it will display the tags on that page number.
            If `detailed` is provided, it will ignore your privacy preferences and display everything. This is automatically true in DMs.
            As of now, this command will not be able to inspect another user's tags.
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

    tag_commands.append(
        make_command(
            {
                "tag info": {
                    "info": [
                        "i"
                    ]
                }
            },
            "Shows you information about a tag.",
            """
            Shows you information about a tag.
            If `detailed` is provided, it will ignore your privacy preferences and display everything. This is automatically true in DMs.
            As of now, this command will not be able to inspect another user's tags.
            """,
            [
                Argument(
                    "tag",
                    ProxyTagStrategy()
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

    tag_commands.append(
        make_command(
            {
                "tag members": {
                    "members": [
                        "m"
                    ]
                }
            },
            "Shows you the proxies with a specific tag.",
            """
            Shows you the proxies with a specific tag.
            If `detailed` is provided, it will ignore your privacy preferences and display everything. This is automatically true in DMs.
            As of now, this command will not be able to inspect another user's proxies.
            """,
            [
                Argument(
                    "tag",
                    ProxyTagStrategy()
                ),
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

    tag_commands.append(
        make_command(
            {
                "tag set name": {
                    "set name": [
                        "name",
                        "n"
                    ]
                }
            },
            "Updates a tag's name.",
            """
            Updates a tag's name.
            """,
            [
                Argument(
                    "tag",
                    ProxyTagStrategy()
                ),
                Argument(
                    "name",
                    str,
                    tag_name_example
                )
            ]
        )
    )

    tag_commands.append(
        make_command(
            {
                "tag set description": {
                    "set description": [
                        "description",
                        "desc"
                    ]
                }
            },
            "Updates a tag's description.",
            """
            Updates a tag's description.
            """,
            [
                Argument(
                    "tag",
                    ProxyTagStrategy()
                ),
                Argument(
                    "description",
                    Optional(
                        StringStrategy("MEDIUM"),
                        ""
                    )
                )
            ]
        )
    )

    tag_commands.append(
        make_command(
            {
                "tag set marker": {
                    "set marker": [
                        "marker",
                        "set tag",
                        "tag"
                    ]
                }
            },
            "Updates a tag's marker.",
            """
            Updates a tag's marker.
            The marker is a template that is used to change how a proxy's name appears on message.
            """,
            [
                Argument(
                    "tag",
                    ProxyTagStrategy()
                ),
                Argument(
                    "marker",
                    Optional(
                        TemplateStrategy([
                            "name",
                            "proxy",
                            "tag",
                            "id",
                            "description",
                            "triggers",
                            "tags",
                            "form",
                            "pronouns",
                        ]),
                        None
                    )
                )
            ]
        )
    )

    tag_commands.append(
        make_command(
            {
                "tag delete": "delete"
            },
            "Deletes a tag.",
            """
            Deletes a tag.
            This action is irreversible.
            """,
            [
                Argument(
                    "tag",
                    ProxyTagStrategy()
                )
            ]
        )
    )
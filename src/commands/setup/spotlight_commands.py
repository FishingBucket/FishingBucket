from ..generic import make_command, Argument, make_command_group
from ..generic.strategies import Optional, List, IntegerStrategy
from ..specific import ProxyStrategy

def setup():
    spotlight_group = make_command_group(
        "spotlight_commands",
        "Spotlight Commands",
        "Commands that configures the spotlight list.",
        {
            "spotlight": [
                "spot",
                "front",
                "switch",
                "switches",
                "sw",
                "sl"
            ]
        }
    )

    spotlight_group.append(make_command(
        {
            "spotlight list": {
                "list": ["l"]
            }
        },
        "Shows your current spotlight.",
        """
        Shows your current spotlight.
        """,
        []
    ))

    spotlight_group.append(make_command(
        {
            "spotlight set": {
                "set": [
                    "=",
                    "s"
                ]
            }
        },
        "Sets your current spotlight.",
        """
        Sets your current spotlight.
        If no proxies are provided, the spotlight will be empty.
        """,
        [
            Argument(
                "proxies",
                Optional(
                    List(
                        ProxyStrategy(),
                        fatal=True
                    ),
                    []
                )
            )
        ]
    ))

    spotlight_group.append(make_command(
        {
            "spotlight add": {
                "add": [
                    "push",
                    "+"
                ]
            }
        },
        "Adds a proxy to your current spotlight.",
        """
        Adds a proxy to your current spotlight.
        """,
        [
            Argument(
                "proxy",
                ProxyStrategy()
            )
        ]
    ))

    spotlight_group.append(make_command(
        {
            "spotlight clear": {
                "clear": [
                    "out"
                ]
            }
        },
        "Clears your current spotlight list.",
        """
        Clears your current spotlight list.
        """,
        []
    ))

    spotlight_group.append(make_command(
        {
            "spotlight pop": {
                "pop": [
                    "-"
                ]
            }
        },
        "Removes the last entered spotlight proxy.",
        """
        Removes the last entered spotlight proxy.
        """,
        []
    ))

    spotlight_group.append(make_command(
        {
            "spotlight insert": {
                "insert": [
                    "ins"
                ]
            }
        },
        "Inserts a proxy into the current spotlight.",
        """
        Inserts a proxy into the current spotlight.
        If not provided, the default index is the first spot.
        """,
        [
            Argument(
                "proxy",
                ProxyStrategy()
            ),
            Argument(
                "index",
                Optional(
                    IntegerStrategy(),
                    1
                )
            )
        ]
    ))

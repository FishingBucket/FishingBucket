from ..generic import make_command_group, make_command, Argument
from ..generic.strategies import Optional, URLStrategy, OptionList


def setup():
    io_group = make_command_group(
        "io_commands",
        "Import / Export Commands",
        "Save or load your data."
    )

    io_group.append(
        make_command(
            "import",
            "Imports proxy data from a file.",
            """
            Imports proxy data from a file.
            This can be used to import from exports done by this bot or other similar programs.
            The export file can be attached as an attachment or send as a link.
            Duplicates are resolved by comparing names.
        
            List of supported import targets:
            - Fishing Bucket (`fishing_bucket`)
            - Tupperbox (`tupperbox`)
            - PluralKit (`pluralkit`)
            - Utter (`utter`)
            - PluralBuddy (`pluralbuddy`) (cannot be inferred)
            - /plu/ral (`/plu/ral`)
            
            If `origin` is not provided, then it will be guessed based on the filename.
            """,
            [
                Argument(
                    "file",
                    Optional(
                        URLStrategy(),
                        None
                    )
                ),
                Argument(
                    "origin",
                    Optional(
                        OptionList(
                            "origin",
                            {
                                "fishing_bucket": [
                                    "fb",
                                    "fish"
                                ],
                                "tupperbox": [
                                    "tul",
                                    "tupper"
                                ],
                                "pluralkit": [
                                    "pk"
                                ],
                                "utter": [],
                                "pluralbuddy": [
                                    "pb"
                                ],
                                "/plu/ral": [
                                    "plural"
                                ]
                            },
                            True
                        ),
                        None
                    )
                )
            ]
        )
    )

    io_group.append(
        make_command(
            "export",
            "Generates an export of your data.",
            """
            Generates an export of your data.
            This includes everything to re-import the proxies and tags back into the bot.
            This format is **not compatible** with any other software.
            """,
            []
        )
    )

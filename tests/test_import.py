import json
import sys
import traceback
from pathlib import Path

from src.backend.database.user import UserID
import src.backend.import_system as import_system
from src.backend.import_system import NativeExporter
from tests.utils import compare_json

pairings: list[tuple[type[import_system.Importer], str, str]] = [
    (import_system.TupperboxImporter, "tupperbox", "export.json"),
    (import_system.PluralKitImporter, "pluralkit-case-sensitive", "export.json"),
    (import_system.PluralKitImporter, "pluralkit-case-insensitive", "export.json"),
    (import_system.NativeImporter, "fishingbucket", "export.json"),
    (import_system.UtterImporter, "utter", "export.json"),
    (import_system.PluralBuddyImporter, "pluralbuddy", "export.json"),
    (import_system.PluRalImporter, "plural", "export.json")
]

wrongs = 0

for importer, directory, export_file in pairings:
    print(f"Testing {directory}")
    try:
        cls = importer()
        path = Path("../test_data") / directory
        with open(path / export_file, "rb") as f:
            data = f.read()

        owner = UserID(0)

        cls.import_data(data, owner)

        with open(path / "final.json") as f:
            final = json.loads(f.read())

        exported = NativeExporter(cls.proxies, cls.tags, cls.relationships)
        exported_data = exported.export_data()
        parsed_exported_data = json.loads(exported_data.decode("utf-8"))

        with open(path / "exported.json", "w") as f:
            f.write(json.dumps(parsed_exported_data, indent=2))

        compare_json([], parsed_exported_data, final)

    except:
        print(f"Failed to import from {directory}")
        print(traceback.format_exc())
        wrongs += 1

sys.exit(wrongs)

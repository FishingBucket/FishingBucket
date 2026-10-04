import json
import asyncio
from pathlib import Path

import aiohttp
import sys

RAW_URL = "https://raw.githubusercontent.com/fluxerapp/fluxer/refs/heads/main/fluxer_app/src/media/data/emojis.json"

print("Downloading emoji data...")
async def download_data() -> dict | None:
    async with aiohttp.ClientSession() as session:
        async with session.get(RAW_URL) as response:
            if response.status != 200:
                return None
            else:
                return json.loads(await response.text(encoding="utf-8"))

raw_emojis = asyncio.run(download_data())
if raw_emojis is None:
    print("Download failed!")
    sys.exit(-1)

print("Download successful.")

type EmojiName = str
type Emoji = str

forward_map: dict[EmojiName, Emoji] = {}
backward_map: dict[Emoji, list[EmojiName]] = {}

for category, emoji_list in raw_emojis["categories"].items():
    print(f"Parsing category {category}...")
    for item in emoji_list:
        for name in item["names"]:
            forward_map[name] = item["surrogates"]
        backward_map[item["surrogates"]] = item["names"]
    print(f"Done! {len(emoji_list)} emojis processed for {category}!")

path = Path(input("Enter path to data directory: ")) / "emojis.json"

print("Writing to emojis.json...")
with open(path, "w+") as file:
    file.write(json.dumps({
        "forward_map": forward_map,
        "backward_map": backward_map
    }))
print("Finished writing!")

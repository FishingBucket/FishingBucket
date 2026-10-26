import uuid

import aiohttp

from ..context import config, context


async def cdn_reupload_file(file_name: str, url: str) -> str:
    if not config().cdn or not context().s3_client:
        return url

    key = uuid.uuid4().hex + "." + file_name.split(".")[-1]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()
    except:
        return url

    cdn_config = config().cdn
    await context().s3_client.put_object(Bucket=cdn_config.s3.bucket_name, Key=key, Body=data)
    return str(cdn_config.url) + key


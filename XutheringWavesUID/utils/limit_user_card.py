import json

import aiofiles

from ..utils.resource.RESOURCE_PATH import MAP_PATH

LIMIT_PATH = MAP_PATH / "1.json"


async def load_limit_user_card():
    """每次读取极限面板数据，不再预加载"""
    async with aiofiles.open(LIMIT_PATH, "r", encoding="UTF-8") as f:
        data = json.loads(await f.read())

    return data

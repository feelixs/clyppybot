from interactions import Message
from bot.env import CLYPPYIO_USER_AGENT, MAX_VIDEO_LEN_SEC, EMBED_W_TOKEN_MAX_LEN, EMBED_TOKEN_COST, DL_SERVER_ID
from typing import Tuple
from os import getenv
import aiohttp


def get_aiohttp_session():
    """Create an aiohttp ClientSession with the ClyppyBot user agent."""
    return aiohttp.ClientSession(headers={"User-Agent": CLYPPYIO_USER_AGENT})


async def fetch_video_status(clip_id: str):
    url = 'https://clyppy.io/api/clips/get-status/'
    headers = {
        'auth': getenv('clyppy_post_key'),
        'Content-Type': 'application/json'
    }
    async with get_aiohttp_session() as session:
        async with session.get(url, json={'clip_id': clip_id}, headers=headers) as response:
            return await response.json()


async def is_404(url: str, logger=None) -> Tuple[bool, int]:
    try:
        async with get_aiohttp_session() as session:
            async with session.get(url) as response:
                if logger is not None:
                    logger.info(f"Got response status {response.status} for {url}")
                return not str(response.status).startswith('2'), response.status
    except aiohttp.ClientError:
        # Handle connection errors, invalid URLs etc
        return True, 500  # Consider failed connections as effectively 404


async def add_reqqed_by(data, key):
    async with get_aiohttp_session() as session:
        async with session.post(
                'https://clyppy.io/api/clips/add-requested-by/',
                json=data,
                headers={
                    'X-API-Key': key,
                    'Content-Type': 'application/json'
                }
        ) as response:
            return await response.json()


async def callback_clip_delete_msg(data, key, ctx_type: str = "StoredVideo") -> dict:
    async with get_aiohttp_session() as session:
        async with session.post(
                'https://clyppy.io/api/clips/msg-get-delete/',
                json=data,
                headers={
                    'X-API-Key': key,
                    'Request-Type': ctx_type,
                    'Content-Type': 'application/json'
                }
        ) as response:
            return await response.json()


async def subtract_tokens(user, amt):
    url = 'https://clyppy.io/api/tokens/subtract/'
    headers = {
        'X-API-Key': getenv('clyppy_post_key'),
        'Content-Type': 'application/json'
    }
    j = {'userid': user.id, 'username': user.username, 'amount': amt}
    async with get_aiohttp_session() as session:
        async with session.post(url, json=j, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_data = await response.json()
                raise Exception(f"Failed to subtract user's VIP tokens: {error_data.get('error', 'Unknown error')}")


async def author_has_premium(user):
    return str(user.id) == '164115540426752001'


async def author_has_enough_tokens(msg, video_dur):
    def is_dl_server(guild):
        if guild is None:
            return False
        elif str(guild.id) == str(DL_SERVER_ID):
            return True
        return False

    if video_dur <= MAX_VIDEO_LEN_SEC:  # no tokens need to be used
        return True
    elif video_dur <= EMBED_W_TOKEN_MAX_LEN:  # use the tokens (the video will embed if they're deducted successfully)
        user = msg.author

        # if we're in dl server, automatically return true without needing any tokens
        if is_dl_server(msg.guild):
            return True

        sub = await subtract_tokens(user, EMBED_TOKEN_COST)
        if sub['success']:
            if sub['user_success']:  # the user had enough tokens to subtract successfully
                return True

    return False

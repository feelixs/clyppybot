from interactions import SlashContext, Message

from bot.env import CLYPPYIO_USER_AGENT, MAX_VIDEO_LEN_SEC, EMBED_W_TOKEN_MAX_LEN, EMBED_TOTAL_MAX_LENGTH, EMBED_TOKEN_COST, DL_SERVER_ID
from typing import Tuple, Union
from math import ceil
from os import getenv
import aiohttp

from bot.errors import VideoLongerThanMaxLength


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


async def push_interaction_error(parent_msg: Union[Message, SlashContext], clip_url, platform_name: str, error_info: dict, handled: bool, clip=None):
    url = 'https://clyppy.io/api/clips/publish/error/'
    headers = {
        'X-API-Key': getenv('clyppy_post_key'),
        'Content-Type': 'application/json'
    }

    video_id = None
    if clip is not None:
        video_id = clip.clyppy_id

    video_platform = platform_name.lower()
    video_url = clip_url
    error_name = error_info['name']
    error_msg = error_info['msg']
    async with get_aiohttp_session() as session:
        async with session.post(url, json={
            'clyppy_id_ctx': video_id,
            'error_type': error_name,
            'error_message': error_msg,
            'video_url': video_url,
            'video_platform': video_platform,
            'username': parent_msg.author.username,
            'user_id': parent_msg.author.id,
            'handled': handled,
        }, headers=headers) as response:
            if response.status != 201:
                raise Exception(f"Failed to push interaction error: {await response.text()}")
            else:
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


async def get_clip_info(clip_id: str, ctx_type='StoredVideo'):
    url = f"https://clyppy.io/api/clips/get/{clip_id}"
    headers = {
        'X-API-Key': getenv('clyppy_post_key'),
        'Request-Type': ctx_type,
        'Content-Type': 'application/json'
    }
    async with get_aiohttp_session() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                j = await response.json()
                return j
            elif response.status == 404:
                return {'match': False}
            else:
                raise Exception(f"Failed to get clip info: (Server returned code: {response.status})")


async def subtract_tokens(user, amt, clip_url: str=None, reason: str=None, description: str=None):
    if reason is None:
        reason = 'Clyppy Embed'

    url = 'https://clyppy.io/api/tokens/subtract/'
    headers = {
        'X-API-Key': getenv('clyppy_post_key'),
        'Content-Type': 'application/json'
    }
    j = {
        'userid': user.id,
        'username': user.username,
        'amount': amt,
        'reason': reason,
        'original_url': clip_url,
        'description': description,
    }
    async with get_aiohttp_session() as session:
        async with session.post(url, json=j, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_data = await response.json()
                raise Exception(f"Failed to subtract user's VIP tokens: {error_data.get('error', 'Unknown error')}")


async def refresh_clip(clip_id: str, user_id: int):
    url = f"https://clyppy.io/api/clips/refresh/{clip_id}"
    head = {
        'X-Discord-User-Id': str(user_id),
        'Not-Encoded': 'true',
        'Ignore-User-Check': 'true'
    }
    async with get_aiohttp_session() as session:
        async with session.post(url, headers=head) as response:
            return await response.json()


async def author_has_premium(user):
    return str(user.id) == '164115540426752001'


def get_token_cost(video_dur):
    """Raises VideoLongerThanMaxLength if video is too long"""
    if video_dur >= EMBED_TOTAL_MAX_LENGTH:
        raise VideoLongerThanMaxLength(video_dur)

    # Free embed up to MAX_VIDEO_LEN_SEC
    if video_dur <= MAX_VIDEO_LEN_SEC:
        return 0

    # Calculate tokens only for the portion exceeding the free limit
    extra_duration = video_dur - MAX_VIDEO_LEN_SEC
    return EMBED_TOKEN_COST * ceil(extra_duration / EMBED_W_TOKEN_MAX_LEN)  # 1 token per 30 minutes of additional time


async def author_has_enough_tokens(msg, video_dur, url: str) -> tuple[bool, int, int]:
    """Returns: bool->can embed video, int->number of tokens used"""
    def is_dl_server(guild):
        if guild is None:
            return False
        elif str(guild.id) == str(DL_SERVER_ID):
            return True
        return False

    user = msg.author
    if video_dur <= MAX_VIDEO_LEN_SEC:  # no tokens need to be used
        return True, 0, video_dur
    elif video_dur < EMBED_TOTAL_MAX_LENGTH:
        # if we're in dl server, automatically return true without needing any tokens (only for videos under 30min)
        if is_dl_server(msg.guild):
            return video_dur <= EMBED_W_TOKEN_MAX_LEN, 0, video_dur

        cost = get_token_cost(video_dur)
        sub = await subtract_tokens(
            user=user,
            amt=cost,
            clip_url=url
        )
        if sub['success']:
            if sub['user_success']:  # the user had enough tokens to subtract successfully
                return True, cost, video_dur

    return False, 0, video_dur

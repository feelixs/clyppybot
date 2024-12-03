import logging
from datetime import datetime, timezone
import os


class KickClip:
    def __init__(self, data, api, twitchDL_path=None):
        self.api = api
        self.logger = logging.getLogger(__name__)
        if twitchDL_path is None:
            twitchDL_path = os.getenv("TWITCH_DL_PATH")
        self.TWITCH_DL = twitchDL_path
        if data is None:
            self.data = None
            self.id, self.url, self.broadcaster_name = None, None, None
            self.created_at, self.language = None, None
            self.game_id, self.thumbnail_url, self.video_id = None, None, None
            self.title, self.language, self.creator_name = None, None, None
            self.vod_offset, self.duration, self.download_prog = None, None, None
            self.broadcaster_id, self.creator_id, self.views = None, None, None
        else:
            self.data = data
            # TODO make a command that finds all clips by creator name
            self.id, self.url, self.broadcaster_name = data['id'], data['url'], data['broadcaster_name']
            self.created_at, self.language = datetime.strptime(data['created_at'], '%Y-%m-%dT%H:%M:%SZ').replace(
                tzinfo=timezone.utc), data['language']
            self.game_id, self.thumbnail_url, self.video_id = data['game_id'], data['thumbnail_url'], data['video_id']
            self.title, self.language, self.creator_name = data['title'], data['language'], data['creator_name']
            self.vod_offset, self.duration = data['vod_offset'], data['duration']
            self.broadcaster_id, self.creator_id = data['broadcaster_id'], data['creator_id']
            self.views = data['view_count']
            self.download_prog = None

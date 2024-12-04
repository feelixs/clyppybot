from datetime import datetime, timezone
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from bot.errors import DriverDownloadFailed, ClipNotExists
from interactions import Message
import concurrent.futures
from typing import Union
import subprocess
import asyncio
import aiohttp
import logging
import os


class TwitchClip:
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
            self.created_at, self.language = datetime.strptime(data['created_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc), data['language']
            self.game_id, self.thumbnail_url, self.video_id = data['game_id'], data['thumbnail_url'], data['video_id']
            self.title, self.language, self.creator_name = data['title'], data['language'], data['creator_name']
            self.vod_offset, self.duration = data['vod_offset'], data['duration']
            self.broadcaster_id, self.creator_id = data['broadcaster_id'], data['creator_id']
            self.views = data['view_count']
            self.download_prog = None

    async def fetch_link_via_chrome(self, text):
        def sync_get_link(query_href_text):
            options = uc.ChromeOptions()
            options.arguments.extend(["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
            driver = uc.Chrome(options=options, version_main=108)
            try:
                driver.get(query_href_text)
                element = driver.find_element(By.CSS_SELECTOR, f"video[src*='{text}']")
                if element:
                    return element.get_attribute("src")
                else:
                    raise DriverDownloadFailed
            except:
                raise DriverDownloadFailed
            finally:
                # this is run regardless of whether the try block is successful, before returning or raising
                driver.quit()
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, sync_get_link, self.url)

    async def download(self, msg_ctx: Message, autocompress=False, filename: Union[str, None] = None):
        split = self.thumbnail_url.split('-preview', 1)
        if len(split) == 2:  # indicates old clip
            mp4_url = split[0] + ".mp4"
        else:  # new clip
            # looks like:
            # https://production.assets.clips.twitchcdn.net/v2/media/InexpensiveAdventurousSpindleWOOP-9qvScUmiS9WL6jrV/9b1dfe61-3a20-4eea-bcf3-9aaef3800e91/video-720.mp4
            mp4_url = await self.fetch_link_via_chrome("production.assets.clips")

        if filename is None:
            filename = "clyppy_" + self.url.split('/')[-1] + ".mp4"

        if not os.path.isfile(filename):
            async with aiohttp.ClientSession() as session:
                async with session.get(mp4_url) as response:
                    with open(filename, 'wb') as fd:
                        while True:
                            chunk = await response.content.read(1024)
                            if not chunk:
                                break
                            fd.write(chunk)
            if not os.path.isfile(filename):
                raise ClipNotExists
            self.logger.info(f"downloaded {filename}")

            # touch the file to update the modified time
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                touch = subprocess.Popen(["touch", os.path.realpath(filename)], stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
                stdout, stderr = await loop.run_in_executor(pool, touch.communicate)

        return filename

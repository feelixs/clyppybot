import undetected_chromedriver as uc
from interactions import Message
from typing import Union
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
import logging
import asyncio
import json
import time
import traceback
import os


class KickClip:
    def __init__(self, slug, user):
        self.id = slug
        self.user = user
        self.logger = logging.getLogger(__name__)

    async def get_m3u8_url(self):
        """Get m3u8 URL using undetected-chromedriver"""
        caps = DesiredCapabilities.CHROME
        caps['goog:loggingPrefs'] = {'performance': 'ALL'}

        options = uc.ChromeOptions()
        options.arguments.extend(["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        driver = uc.Chrome(options=options, desired_capabilities=caps, version_main=108)
        self.logger.info("Started browser and monitoring network...")

        async def scan_logs_for_m3u8(driver, timeout=10):
            start_time = time.time()
            while time.time() - start_time < timeout:
                browser_log = driver.get_log('performance')
                for entry in browser_log:
                    event = json.loads(entry['message'])['message']
                    try:
                        if ('Network.requestWillBeSent' == event['method']
                                and 'request' in event['params']
                                and 'url' in event['params']['request']):
                            url = event['params']['request']['url']
                            if 'playlist.m3u8' in url:
                                self.logger.info(f"Found m3u8 URL: {m3u8_url} after {time.time() - start_time}")
                                return url
                    except Exception:
                        continue
                await asyncio.sleep(0.5)  # Short sleep to prevent CPU thrashing
            return None

        try:
            clip_url = f"https://kick.com/{self.user}/clips/clip_{self.id}"
            driver.get(clip_url)

            m3u8_url = await scan_logs_for_m3u8(driver)
            if m3u8_url:
                return m3u8_url

            self.logger.error("No m3u8 URL found in logs")
            return None

        except Exception as e:
            self.logger.error(traceback.format_exc())
            return None
        finally:
            driver.quit()

    async def download(self, msg_ctx: Message, autocompress=False, filename: Union[str, None] = None):
        if filename is None:
            filename = f"clip_{self.id}.mp4"
        if os.path.isfile(filename):
            self.logger.info(f"File `{filename}` already exists, no need to download")
            return filename

        m3u8_url = await self.get_m3u8_url()
        if not m3u8_url:
            self.logger.error("Failed to get m3u8 URL")
            return None

        # Download using ffmpeg
        try:
            command = [
                'ffmpeg',
                '-i', m3u8_url,
                '-c', 'copy',
                filename
            ]

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await process.communicate()

            if process.returncode != 0:
                self.logger.error("FFmpeg download failed")
                return None

            return filename

        except Exception as e:
            self.logger.error(f"Error downloading clip: {e}")
            return None
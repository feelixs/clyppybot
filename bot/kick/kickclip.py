import undetected_chromedriver as uc
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
import logging
import asyncio
import json
import traceback


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

        driver = uc.Chrome(options=options, desired_capabilities=caps)
        self.logger.info("Started browser and monitoring network...")

        try:
            clip_url = f"https://kick.com/{self.user}/clips/clip_{self.id}"
            driver.get(clip_url)

            def logs_have_enough_events(driver):
                browser_log = driver.get_log('performance')
                events = [json.loads(entry['message'])['message'] for entry in browser_log]
                return len(events) > 50  # Adjust this threshold based on testing

            # Wait up to 5 seconds for enough events, checking every 0.5 seconds
            WebDriverWait(driver, 5, poll_frequency=0.5).until(logs_have_enough_events)

            browser_log = driver.get_log('performance')
            events = [json.loads(entry['message'])['message'] for entry in browser_log]

            for event in events:
                try:
                    if ('Network.requestWillBeSent' == event['method']
                            and 'request' in event['params']
                            and 'url' in event['params']['request']):
                        url = event['params']['request']['url']
                        if 'playlist.m3u8' in url:
                            self.logger.info(f"Found m3u8 URL: {url}")
                            return url
                except Exception as e:
                    continue

            self.logger.error("No m3u8 URL found in logs")
            return None

        except Exception as e:
            self.logger.error(traceback.format_exc())
            return None
        finally:
            driver.quit()

    async def download(self, filename=None):
        if filename is None:
            filename = f"clip_{self.id}.mp4"

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
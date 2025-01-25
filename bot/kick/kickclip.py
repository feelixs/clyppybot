import undetected_chromedriver as uc
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from typing import Optional
import asyncio
import json
import time
import traceback
from bot.classes import BaseClip, upload_video, DownloadResponse, get_video_details


class KickClip(BaseClip):
    def __init__(self, slug, user):
        self._service = "kick"
        self._url = f"https://kick.com/{user}/clips/clip_{slug}"
        self.user = user
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def get_m3u8_url(self):
        """Get m3u8 URL using undetected-chromedriver"""
        caps = DesiredCapabilities.CHROME
        caps['goog:loggingPrefs'] = {'performance': 'ALL'}

        options = uc.ChromeOptions()
        options.arguments.extend(["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        driver = uc.Chrome(options=options, desired_capabilities=caps, version_main=108)
        self.logger.info(f"Started browser and monitoring network on url: {self.url}...")

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
                self.logger.info(f"Found m3u8 URL: {m3u8_url}")
                return m3u8_url

            self.logger.error("No m3u8 URL found in logs")
            return None

        except Exception as e:
            self.logger.error(traceback.format_exc())
            return None
        finally:
            driver.quit()

    async def download(self, filename: str = None, dlp_format='best/bv*+ba') -> Optional[DownloadResponse]:
        try:
            m3u8_url = await self.get_m3u8_url()
        except:
            m3u8_url = None
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

            self.logger.info(f"Uploading the downloaded yt video to https://clyppy.io/api/addclip/: {filename}")
            try:
                response = await upload_video(filename)
            except Exception as e:
                self.logger.error(f"Failed to upload video: {str(e)}")
                return None
            if response['success']:
                self.logger.info(f"Uploaded video: {response['file_path']}")
                i = get_video_details(filename)
                return DownloadResponse(
                    remote_url=response['file_path'],
                    local_file_path=filename,
                    duration=i.duration,
                    filesize=i.filesize,
                    height=i.height,
                    width=i.width,
                    video_name=None
                )
            else:
                self.logger.error(f"Failed to upload video: {response}")
                return None

        except Exception as e:
            self.logger.error(f"Error downloading clip: {e}")
            return None

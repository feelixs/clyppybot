import os.path

import undetected_chromedriver as uc
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from typing import Optional, Tuple
import asyncio
import json
import time
import traceback
from bot.classes import (BaseClip, upload_video, DownloadResponse, get_video_details, MAX_FILE_SIZE_FOR_DISCORD,
                         ClipFailure, is_discord_compatible)


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

    async def get_m3u8_url(self) -> Tuple[str, str]:
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
                self.logger.info(driver.page_source)
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
            try:
                clip_name = driver.find_element(By.XPATH, '/html/body/div[1]/div[2]/div[4]/div[1]/main/div[2]/div[1]/div/div[1]/div[2]/div[1]/span').text
            except Exception as e:
                self.logger.info(f"Could not find title of kick clip: {str(e)}, using default value")
                clip_name = "Clyppy Video"
            if m3u8_url:
                self.logger.info(f"Found m3u8 URL: {m3u8_url}. Clip name: {clip_name}")
                return m3u8_url, clip_name

            self.logger.error("No m3u8 URL found in logs")
            return None, None

        except Exception as e:
            self.logger.error(traceback.format_exc())
            return None, None
        finally:
            driver.quit()

    async def download(self, filename: str = None, dlp_format='best/bv*+ba', can_send_files=False) -> DownloadResponse:
        try:
            m3u8_url, name = await self.get_m3u8_url()
        except:
            m3u8_url, name = None, None
        if not m3u8_url:
            self.logger.error("Failed to get m3u8 URL")
            raise ClipFailure

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
                raise ClipFailure

            if is_discord_compatible(os.path.getsize(filename)) and can_send_files:
                i = get_video_details(filename)
                i.video_name = name
                return DownloadResponse(
                    remote_url=None,
                    local_file_path=filename,
                    duration=i.duration,
                    filesize=i.filesize,
                    height=i.height,
                    width=i.width,
                    video_name=name,
                    can_be_uploaded=True
                )
            else:
                self.logger.info(f"Uploading the downloaded kick video to https://clyppy.io/api/addclip/: {filename}")
                try:
                    response = await upload_video(filename, self.logger)
                except Exception as e:
                    self.logger.error(f"Failed to upload video: {str(e)}")
                    raise ClipFailure
                if response['success']:
                    self.logger.info(f"Uploaded video: {response['file_path']}")
                    i = get_video_details(filename)
                    i.video_name = name
                    return DownloadResponse(
                        remote_url=response['file_path'],
                        local_file_path=filename,
                        duration=i.duration,
                        filesize=i.filesize,
                        height=i.height,
                        width=i.width,
                        video_name=name,
                        can_be_uploaded=False
                    )
                else:
                    self.logger.error(f"Failed to upload video: {response}")
                    raise ClipFailure

        except Exception as e:
            self.logger.error(f"Error downloading clip: {e}")
            raise ClipFailure

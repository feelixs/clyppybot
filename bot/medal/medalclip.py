import undetected_chromedriver as uc
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import logging
import asyncio
import json
import time
import re
import os


class MedalClip:
    def __init__(self, slug):
        self.id = slug
        self.url = f"https://medal.tv/clips/{slug}"
        self.logger = logging.getLogger(__name__)

    async def get_m3u8_url(self):
        """Extract the m3u8 URL from the page"""
        caps = DesiredCapabilities.CHROME
        caps['goog:loggingPrefs'] = {'performance': 'ALL'}

        options = uc.ChromeOptions()
        options.arguments.extend([
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage"
        ])
        options.set_capability('goog:loggingPrefs', caps['goog:loggingPrefs'])

        driver = uc.Chrome(options=options, desired_capabilities=caps, version_main=131)
        self.logger.info("Started browser...")

        try:
            driver.get(self.url)
            start_time = time.time()

            self.logger.info("Scanning for m3u8 URL...")
            # Look for the master m3u8 for 10 seconds
            while time.time() - start_time < 10:
                logs = driver.get_log('performance')
                for entry in logs:
                    event = json.loads(entry['message'])['message']
                    if event.get('method') == 'Network.requestWillBeSent':
                        request = event.get('params', {}).get('request', {})
                        url = request.get('url', '')

                        # Check for master m3u8
                        if 'master.m3u8' in url and 'medal.tv/api/hls' in url:
                            return url

                await asyncio.sleep(0.1)

            return None

        except Exception as e:
            self.logger.error(f"Error getting m3u8 URL: {e}")
            return None
        finally:
            driver.quit()

    async def download(self, output_filename: str = None):
        """Download the video using ffmpeg"""
        # Get the m3u8 URL
        m3u8_url = await self.get_m3u8_url()
        if not m3u8_url:
            self.logger.error("Could not find m3u8 URL")
            return None

        # Extract clip ID for default filename
        clip_id = re.search(r'clips/([^/?]+)', self.url)
        if not output_filename:
            output_filename = f"medal_{clip_id.group(1) if clip_id else 'video'}.mp4"

        self.logger.info(f"Found m3u8 URL: {m3u8_url}")
        self.logger.info(f"Downloading to: {output_filename}")

        # Download using ffmpeg
        try:
            # Construct ffmpeg command
            command = [
                'ffmpeg',
                '-i', m3u8_url,
                '-c', 'copy',  # Copy streams without re-encoding
                '-bsf:a', 'aac_adtstoasc',  # Fix audio stream
                output_filename
            ]

            # Create subprocess
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait for completion
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.error(f"FFmpeg error: {stderr.decode()}")
                return None

            if os.path.exists(output_filename):
                self.logger.info(f"Successfully downloaded: {output_filename}")
                return output_filename
            else:
                self.logger.error("Download completed but file not found")
                return None

        except Exception as e:
            self.logger.error(f"Error during download: {e}")
            return None

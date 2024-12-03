import logging
from typing import Union
from interactions import Message
import os
import requests
import subprocess
import time
import undetected_chromedriver as uc


class KickClip:
    def __init__(self, slug, user):
        self.id = slug
        self.user = user
        self.logger = logging.getLogger(__name__)
        self._setup_logging()

    def _setup_logging(self):
        """Setup logging configuration"""
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def get_fresh_cookies(self):
        """Uses undetected-chromedriver to get fresh cookies bypassing Cloudflare"""
        self.logger.info("Getting fresh cookies...")
        options = uc.ChromeOptions()
        options.arguments.extend(["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])

        try:
            driver = uc.Chrome(options=options)  # Will auto-detect Chrome version

            # Load the clip page
            clip_url = f"https://kick.com/{self.user}/clips/clip_{self.id}"
            self.logger.debug(f"Loading page: {clip_url}")
            driver.get(clip_url)

            # Wait a bit for Cloudflare and page to load
            driver.implicitly_wait(10)

            # Get all cookies
            cookies = driver.get_cookies()

            # Get auth token - might be in localStorage or cookies
            auth_token = driver.execute_script("return localStorage.getItem('auth_token')")

            # Convert cookies to header format
            cookie_string = '; '.join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])

            self.logger.debug("Successfully got fresh cookies")
            return {
                'Cookie': cookie_string,
                'Authorization': f'Bearer {auth_token}' if auth_token else None
            }

        except Exception as e:
            self.logger.error(f"Error getting fresh cookies: {e}")
            return None
        finally:
            if 'driver' in locals():
                driver.quit()

    def _trigger_download(self):
        """Triggers the download generation via Kick's API with fresh cookies"""
        # Get fresh cookies and auth
        fresh_headers = self.get_fresh_cookies()
        if not fresh_headers:
            self.logger.error("Failed to get fresh cookies")
            return False

        headers = {
            'Host': 'kick.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': f'https://kick.com/{self.user}/clips/clip_{self.id}',
            'cluster': 'v2',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Cache-Control': 'max-age=0',
            'TE': 'trailers'
        }

        # Update headers with fresh cookies and auth
        headers.update(fresh_headers)

        url = f"https://kick.com/api/v2/clips/clip_{self.id}/download"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            self.logger.debug(f"Response status: {response.status_code}")
            self.logger.debug(f"Response content-type: {response.headers.get('content-type')}")
            self.logger.debug(f"Response content: {response.text[:200]}")
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error triggering download generation: {e}")
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error(f"Response status: {e.response.status_code}")
                self.logger.error(f"Response headers: {e.response.headers}")
                self.logger.error(f"Response content: {e.response.text[:200]}")
            return False

    def download(self, msg_ctx: Message, autocompress=False, filename: Union[str, None] = None):
        """Downloads the clip after triggering the download generation"""
        # First trigger the download generation
        if not self._trigger_download():
            return None

        # Wait a bit for the file to be generated
        time.sleep(4)  # Adjust this delay if needed

        # Required headers for download
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br'
        }

        # Construct download URL
        download_url = f"https://clips.kick.com/tmp/clip_{self.id}.mp4"

        try:
            # Stream the download
            response = requests.get(download_url, headers=headers, stream=True)
            response.raise_for_status()

            # Get filename from Content-Disposition header or use clip ID
            if not filename:
                filename = f"clip_{self.id}.mp4"

            # Download with progress tracking
            file_size = int(response.headers.get('content-length', 0))
            block_size = 1024  # 1KB blocks

            self.logger.info(f"Downloading {filename} ({file_size / 1024 / 1024:.1f} MB)")

            with open(filename, 'wb') as f:
                downloaded = 0
                for data in response.iter_content(block_size):
                    f.write(data)
                    downloaded += len(data)
                    progress = (downloaded / file_size) * 100
                    print(f"\rProgress: {progress:.1f}%", end="")

            self.logger.info("\nDownload complete!")

            # touch the file to update the modified time
            touch = subprocess.Popen(["touch", os.path.realpath(filename)],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
            touch.communicate()
            return filename

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error downloading clip: {e}")
            return None


if __name__ == "__main__":
    # Example usage
    clip_id = "01J9HF8GTSS5MP083YXGJ2WE2X"  # Replace with actual clip ID
    clip = KickClip(clip_id, 'xqc')
    result = clip.download(None)  # Pass None for msg_ctx when testing
    if result:
        print(f"Successfully downloaded to: {result}")
    else:
        print("Download failed")

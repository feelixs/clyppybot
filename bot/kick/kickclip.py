import logging
from typing import Union
from interactions import Message
from datetime import datetime, timezone
import os
import requests
import subprocess


class KickClip:
    def __init__(self, slug):
        self.id = slug
        self.logger = logging.getLogger(__name__)

    def download(self, msg_ctx: Message, autocompress=False, filename: Union[str, None] = None):
        # Required headers (based on browser request)
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
            response.raise_for_status()  # Raises an HTTPError for bad responses

            # Get filename from Content-Disposition header or use clip ID
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
            self.logger.info(f"Error downloading clip: {e}")
            return None

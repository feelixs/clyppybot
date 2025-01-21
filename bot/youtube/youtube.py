import logging
import yt_dlp
import asyncio
import os
import re
from bot.classes import BaseClip, BaseMisc, DownloadResponse, upload_video, get_video_details, LocalFileInfo
from typing import Optional


class YtMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "YouTube"

    def parse_clip_url(self, url: str) -> Optional[str]:
        """
            Extracts the video ID from a YouTube URL if present.
            Works with all supported URL formats.
        """
        # Common YouTube URL patterns
        patterns = [
            r'^(?:https?://)?(?:www\.)?(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/ ]{11})',
            # Standard and embedded URLs
            r'^(?:https?://)?(?:www\.)?(?:youtube\.com/shorts/)([^"&?/ ]{11})'  # Shorts URLs
        ]

        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str) -> Optional['YtClip']:
        slug = self.parse_clip_url(url)
        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            return None
        self.logger.info(f"{url} is_shortform=True")

        return YtClip(slug, bool(re.search(r'youtube\.com/shorts/', url)))


class YtClip(BaseClip):
    def __init__(self, slug, short):
        self._service = "youtube"
        if short:
            self._url = f"https://youtube.com/shorts/{slug}"
        else:
            self._url = f"https://youtube.com/watch/?v={slug}"
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename=None, dlp_format='best/bv*+ba') -> Optional[DownloadResponse]:
        ydl_opts = {
            'format': dlp_format,
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True,
        }

        try:
            # First extract info to check duration
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: ydl.extract_info(self.url, download=False)
                )

                # Check if duration exists and is longer than 120 seconds
                if 'duration' in info and info['duration'] > 120:
                    self.logger.info(f"Video duration {info['duration']}s exceeds 120s limit")
                    return None
                elif 'duration' not in info:
                    self.logger.info(f"Video duration not found")
                    return None
                self.logger.info(f"Video duration {info['duration']}s is acceptable")
                # Proceed with download if duration is acceptable
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: ydl.download([self.url])
                )

            if os.path.exists(filename):
                self.logger.info(f"Uploading the downloaded yt video to https://clyppy.io/api/addclip/: {filename}")
                i = get_video_details(filename)
                i.height = 720
                i.width = 1280
                return await self.upload_to_clyppyio(i)

            self.logger.info(f"Could not find file")
            return None
        except Exception as e:
            self.logger.error(f"error: {str(e)}")
            return None

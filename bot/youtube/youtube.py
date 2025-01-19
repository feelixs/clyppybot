import logging
import yt_dlp
import asyncio
import os
import re
from bot.classes import BaseClip, BaseMisc, DownloadResponse, upload_video
from typing import Optional


class YtMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "YouTube"
        self.silence_invalid_url = True

    def parse_clip_url(self, url: str) -> Optional[str]:
        """
            Extracts the video ID from a YouTube URL if present.
            Works with all supported URL formats.
        """
        # Common YouTube URL patterns
        patterns = [
            r'(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/ ]{11})',
            # Standard and embedded URLs
            r'(?:youtube\.com/shorts/)([^"&?/ ]{11})'  # Shorts URLs
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
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
        super().__init__(slug)
        self.service = "youtube"
        if short:
            self.url = f"https://youtube.com/shorts/{slug}"
        else:
            self.url = f"https://youtube.com/watch/?v={slug}"

    async def download(self, filename=None, dlp_format='best[ext=mp4]') -> Optional[DownloadResponse]:
        ydl_opts = {
            'format': 'best',
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

                # Check if duration exists and is longer than 60 seconds
                if 'duration' in info and info['duration'] > 60:
                    self.logger.info(f"Video duration {info['duration']}s exceeds 60s limit")
                    return None
                elif 'duration' not in info:
                    self.logger.info(f"Video duration not found")
                    return None

                # Proceed with download if duration is acceptable
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: ydl.download([self.url])
                )

            if os.path.exists(filename):
                try:
                    response = await upload_video(filename)
                except Exception as e:
                    self.logger.error(f"Failed to upload video: {str(e)}")
                    return None
                if response['success'] == 'success':
                    self.logger.info(f"Uploaded video: {response['file_path']}")
                    return DownloadResponse(
                        remote_url=response['file_path'],
                        local_file_path=filename,
                        duration=info['duration']
                    )
                else:
                    self.logger.error(f"Failed to upload video: {response}")
                    return None
            self.logger.info(f"Could not find file")
            return None
        except Exception as e:
            self.logger.error(f"yt-dlp download error: {str(e)}")
            return None

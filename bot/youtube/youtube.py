import logging
import yt_dlp
import asyncio
import os
import re
from bot.classes import (BaseClip, BaseMisc, DownloadResponse, get_video_details, is_discord_compatible, InvalidClipType,
                         MAX_VIDEO_LEN_SEC, VideoTooLong, ClipFailure, NoDuration, MAX_FILE_SIZE_FOR_DISCORD)


class YtMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "YouTube"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> str:
        """
            Extracts the video ID from a YouTube URL if present.
            Works with all supported URL formats.
        """
        # Common YouTube URL patterns
        patterns = [
            r'^(?:https?://)?(?:(?:www|m)\.)?(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/ ]{11})',
            r'^(?:https?://)?(?:(?:www|m)\.)?(?:youtube\.com/shorts/)([^"&?/ ]{11})',
            r'^(?:https?://)?(?:(?:www|m)\.)?youtube\.com/clip/([^"&?/ ]{11})'
        ]

        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        raise InvalidClipType

    async def get_clip(self, url: str, extended_url_formats=False) -> 'YtClip':
        slug = self.parse_clip_url(url)
        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
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

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> DownloadResponse:
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

                # Check if duration exists and is longer than max seconds
                if 'duration' in info and info['duration'] > MAX_VIDEO_LEN_SEC:
                    self.logger.info(f"Video duration {info['duration']}s exceeds {MAX_VIDEO_LEN_SEC}s limit")
                    raise VideoTooLong
                elif 'duration' not in info:
                    self.logger.info(f"Video duration not found")
                    raise NoDuration
                self.logger.info(f"Video duration {info['duration']}s is acceptable")
                # Proceed with download if duration is acceptable
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: ydl.download([self.url])
                )

            if os.path.exists(filename):
                extracted = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._extract_info,
                    ydl_opts
                )

                d = get_video_details(filename)
                d.video_name = extracted.video_name

                if is_discord_compatible(d.filesize) and can_send_files:
                    self.logger.info("The downloaded yt video can fit into a discord upload")
                    return DownloadResponse(
                        remote_url=None,
                        local_file_path=filename,
                        duration=d.duration,
                        width=d.width,
                        height=d.height,
                        filesize=d.filesize,
                        video_name=d.video_name,
                        can_be_uploaded=True
                    )
                else:
                    self.logger.info(f"Uploading the downloaded yt video to https://clyppy.io/api/addclip/: {filename}")
                    return await self.upload_to_clyppyio(d)

            self.logger.info(f"Could not find file")
            raise ClipFailure
        except Exception as e:
            self.logger.error(f"error: {str(e)}")
            raise ClipFailure

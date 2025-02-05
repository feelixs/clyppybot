import asyncio
import os
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import clips_array
import time
from bot.classes import BaseClip, DownloadResponse, InvalidClipType, MAX_FILE_SIZE_FOR_DISCORD
from bot.twitch.api import TwitchAPI
import concurrent.futures
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs
from yt_dlp import YoutubeDL


class TwitchClip(BaseClip):
    def __init__(self, slug):
        self._service = "twitch"
        self._url = f"https://clips.twitch.tv/{slug}"
        super().__init__(slug)
        self.api = TwitchAPI(
            key=os.getenv("CLYPP_TWITCH_ID"),
            secret=os.getenv("CLYPP_TWITCH_SECRET"),
            logger=self.logger,
            log_path=os.path.join('logs', 'twitch-api-usage.log')
        )

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def fetch_data(self) -> 'TwitchClipProcessor':
        info = await self.api.get("https://api.twitch.tv/helix/clips?id=" + self.id)
        self.logger.info(info)
        return TwitchClipProcessor(
            data=info['data'][0],
            api=self.api,
            logger=self.logger
        )

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> Optional[DownloadResponse]:
        try:
            media_assets_url = self._get_direct_clip_url()
            ydl_opts = {
                'format': dlp_format,
                'quiet': True,
                'no_warnings': True,
            }
            extracted = await asyncio.get_event_loop().run_in_executor(
                None,
                self._extract_info,
                ydl_opts
            )
            extracted.remote_url = media_assets_url
            if MAX_FILE_SIZE_FOR_DISCORD > extracted.filesize > 0 and can_send_files:
                return await super().dl_download(filename, dlp_format, can_send_files)
            else:
                extracted.filesize = 0  # bc its hosted on twitch, not clyppy.io
                return extracted
        except InvalidClipType:
            # download temporary v2 link (default)
            return await super().download(filename=filename, dlp_format=dlp_format, can_send_files=can_send_files)

    def _get_direct_clip_url(self):
        # only works for some twitch clip links
        # for some reason only some twitch links are type media-assets2
        # and others use https://static-cdn.jtvnw.net/twitch-clips-thumbnails-prod/, which idk yet how to directly link the perm mp4 link
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if not info.get('thumbnail'):
                    raise Exception("No thumbnail URL found in clip info")
                thumbnail_url = info['thumbnail']
                if '/clips-media-assets2.twitch.tv/' not in thumbnail_url:
                    raise InvalidClipType

                self.logger.info(f"{self.id} is of type media-assets2, parsing direct URL...")
                mp4_url = re.sub(r'-preview-\d+x\d+\.jpg$', '.mp4', thumbnail_url)
                return mp4_url
        except InvalidClipType:
            raise
        except Exception as e:
            raise Exception(f"Failed to extract clip URL: {str(e)}")


class TwitchClipProcessor:
    def __init__(self, data: Optional[Dict[str, Any]], api: Any, logger: Any):
        """
        Initialize TwitchClipProcessor with clip data, API client, and logger

        Args:
            data: Dictionary containing clip metadata
            api: Twitch API client
            logger: Logger instance
        """
        self.logger = logger
        self.api = api
        self.TWITCH_DL = os.getenv("TWITCH_DL_PATH")

        if not self.TWITCH_DL:
            raise ValueError("TWITCH_DL_PATH environment variable not set")

        if not os.path.exists(self.TWITCH_DL):
            raise FileNotFoundError(f"Twitch downloader not found at {self.TWITCH_DL}")

        # Initialize attributes with None
        self.data = None
        self._init_attributes()

        # If data provided, populate attributes
        if data:
            self.data = data
            self._populate_attributes(data)

    def _init_attributes(self) -> None:
        """Initialize all attributes to None"""
        attrs = ['id', 'url', 'broadcaster_name', 'created_at', 'language',
                 'game_id', 'thumbnail_url', 'video_id', 'title', 'creator_name',
                 'vod_offset', 'duration', 'broadcaster_id', 'creator_id', 'views']
        for attr in attrs:
            setattr(self, attr, None)

    def _populate_attributes(self, data: Dict[str, Any]) -> None:
        """Populate attributes from data dictionary"""
        self.id = data['id']
        self.url = data['url']
        self.broadcaster_name = data['broadcaster_name']
        self.created_at = datetime.strptime(
            data['created_at'],
            '%Y-%m-%dT%H:%M:%SZ'
        ).replace(tzinfo=timezone.utc)
        self.language = data['language']
        self.game_id = data['game_id']
        self.thumbnail_url = data['thumbnail_url']
        self.video_id = data['video_id']
        self.title = data['title']
        self.creator_name = data['creator_name']
        self.vod_offset = data['vod_offset']
        self.duration = data['duration']
        self.broadcaster_id = data['broadcaster_id']
        self.creator_id = data['creator_id']
        self.views = data['view_count']

    async def _download_chat(self, outfile: Optional[str] = None) -> str:
        """
        Download chat for the clip

        Args:
            outfile: Optional output file path for chat JSON

        Returns:
            Path to downloaded chat JSON file
        """
        if not self.video_id:
            raise ValueError("No video_id available")

        outfile = outfile or f"{self.id}.json"
        outfile = os.path.abspath(outfile)

        async def run_download() -> None:
            try:
                cmd = [
                    self.TWITCH_DL,
                    "--mode", "chatdownload",
                    "--id", str(self.video_id),
                    "--output", outfile,
                    "--beginning", f"{self.vod_offset}s",
                    "--ending", f"{int(self.vod_offset) + int(self.duration)}s",
                    "--collision", "exit",
                ]
                self.logger.info(" ".join(cmd))

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    raise RuntimeError(f"Chat download failed: {stderr.decode()}")

            except Exception as e:
                self.logger.error(f"Error downloading chat: {str(e)}")
                raise

        await run_download()
        return outfile

    async def _render_chat(self, infile: str, outfile: str) -> str:
        """
        Render chat JSON to video

        Args:
            infile: Path to input chat JSON file
            outfile: Path to output video file

        Returns:
            Path to rendered chat video file
        """
        infile = os.path.abspath(infile)
        outfile = os.path.abspath(outfile)

        if not os.path.exists(infile):
            raise FileNotFoundError(f"Chat JSON file not found: {infile}")

        async def run_render() -> None:
            try:
                cmd = [
                    self.TWITCH_DL,
                    "--mode", "chatrender",
                    "-i", infile,
                    "-o", outfile,
                    "-h", "1080"
                ]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    raise RuntimeError(f"Chat render failed: {stderr.decode()}")

            except Exception as e:
                self.logger.error(f"Error rendering chat: {str(e)}")
                raise

        await run_render()
        return outfile

    async def _combine_videos(self, clip_path: str, chat_path: str, output_path: str) -> str:
        """
        Combine clip and chat videos side by side

        Args:
            clip_path: Path to clip video file
            chat_path: Path to chat video file
            output_path: Path for combined output video

        Returns:
            Path to combined video file
        """

        def run_combine() -> None:
            try:
                clip1 = VideoFileClip(clip_path)
                clip2 = VideoFileClip(chat_path)

                final_clip = clips_array([[clip1, clip2]])

                start_time = time.time()
                final_clip.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    preset='faster',
                    threads=8,
                    fps=24,
                    bitrate="3140k",
                    audio_bitrate="192k",
                    logger=None
                )

                duration = time.time() - start_time
                file_size = os.path.getsize(output_path)

                self.logger.info(
                    f"Video combination complete: size={file_size}, "
                    f"duration={self.duration}, processing_time={duration:.2f}s"
                )

                # Clean up movie clips
                clip1.close()
                clip2.close()

            except Exception as e:
                self.logger.error(f"Error combining videos: {str(e)}")
                raise

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, run_combine)

        return output_path

    async def add_chat(self, clip_path: str) -> str:
        """
        Add chat to a clip video

        Args:
            clip_path: Path to the original clip video file

        Returns:
            Path to final video with chat
        """
        self.logger.info(f"Beginning chat add for {self.url}")

        # Setup paths
        clip_path = os.path.abspath(clip_path)
        base_path = Path(clip_path)
        chat_video_path = str(base_path.parent / f"{base_path.stem}_chat{base_path.suffix}")

        # If already processed, return existing file
        if os.path.isfile(chat_video_path):
            self.logger.info("Chat video already exists")
            return chat_video_path

        try:
            # Download and render chat
            self.logger.info("Downloading chat...")
            chat_json = await self._download_chat()
            self.logger.info("Rendering chat...")
            chat_render = await self._render_chat(
                infile=chat_json,
                outfile=str(base_path.parent / f"rendered_{base_path.name}")
            )
            self.logger.info("Combining videos...")
            # Combine videos
            final_video = await self._combine_videos(
                clip_path=clip_path,
                chat_path=chat_render,
                output_path=chat_video_path
            )
            self.logger.info("Cleanup...")
            # Cleanup temporary files
            for file in [chat_json, chat_render]:
                try:
                    os.remove(file)
                except OSError as e:
                    self.logger.warning(f"Error removing temporary file {file}: {e}")
            self.logger.info("Done")
            return final_video

        except Exception as e:
            self.logger.error(f"Failed to add chat to video: {str(e)}")
            raise

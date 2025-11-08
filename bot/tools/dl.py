from bot.types import DownloadResponse, LocalFileInfo
from bot.errors import UnknownError, VideoTooLongForExtend, VideoTooShortForExtend, VideoExtensionFailed
from bot.classes import BaseClip
from pathlib import Path
from typing import Union
from moviepy import VideoFileClip
import asyncio
import os
import re


class DownloadManager:
    def __init__(self, p):
        self._parent = p
        max_concurrent = os.getenv('MAX_RUNNING_AUTOEMBED_DOWNLOADS', 5)
        self._semaphore = asyncio.Semaphore(int(max_concurrent))

    async def download_clip(
            self,
            clip: BaseClip,
            can_send_files=False,
            skip_upload=False,
            extend_with_ai=False
    ) -> Union[DownloadResponse, LocalFileInfo]:
        desired_filename = f'{clip.service}_{clip.clyppy_id}' if clip.service != 'base' else f'{clip.clyppy_id}'
        if len(desired_filename) > 200:
            desired_filename = desired_filename[:200]
        desired_filename += ".mp4"
        async with self._semaphore:
            if not isinstance(clip, BaseClip):
                raise TypeError(f"Invalid clip object passed to download_clip of type {type(clip)}")
            self._parent.logger.info("Run clip.download()")
        if skip_upload:
            # force manual override of auto-upload (download() may upload, but dl_download() doesn't)
            r: LocalFileInfo = await clip.dl_download(filename=desired_filename, can_send_files=can_send_files)
        else:
            r: DownloadResponse = await clip.download(filename=desired_filename, can_send_files=can_send_files)

        if extend_with_ai:
            new_duration = await self._extend_video_with_ai(r.local_file_path)
            r.duration = new_duration

        if r is None:
            raise UnknownError
        return r

    async def _extend_video_with_ai(self, input_file: str) -> float:
        """
        Extend a video using AI models with Sora->Veo fallback

        Args:
            input_file: Path to the video file to extend (will be overwritten)

        Returns:
            New video duration in seconds

        Raises:
            VideoTooLongForExtend: If video is longer than 60 seconds
            VideoTooShortForExtend: If video is shorter than 6 seconds
            VideoExtensionFailed: If all models fail
        """
        self._parent.logger.info("Extending video with AI...")

        # Try Sora first, then fallback to Veo
        models_to_try = ['sora', 'veo']
        last_error = None

        for model in models_to_try:
            try:
                self._parent.logger.info(f"Attempting video extension with model: {model}")

                # Run the extend_video.py script as a subprocess
                process = await asyncio.create_subprocess_exec(
                    'python', (Path(__file__).parent.parent / 'scripts/extend_video.py'),
                    input_file,
                    '--output', input_file,  # Overwrite the original file
                    '--model', model,
                    '--duration', '8',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()
                stdout_text = stdout.decode('utf-8')
                stderr_text = stderr.decode('utf-8')

                # Check for errors in output
                if process.returncode != 0:
                    combined_output = stdout_text + stderr_text

                    # Check for duration validation errors
                    if 'Input video is too long' in combined_output:
                        # Extract duration from error message
                        match = re.search(r'Input video is too long: ([\d.]+)s', combined_output)
                        video_dur = float(match.group(1)) if match else 0
                        raise VideoTooLongForExtend(video_dur)

                    if 'Input video is too short' in combined_output:
                        # Extract duration from error message
                        match = re.search(r'Input video is too short: ([\d.]+)s', combined_output)
                        video_dur = float(match.group(1)) if match else 0
                        raise VideoTooShortForExtend(video_dur)

                    # Check for moderation block (Sora-specific)
                    if 'moderation_blocked' in combined_output or 'moderation system' in combined_output:
                        self._parent.logger.warning(f"Video blocked by {model} moderation, trying next model...")
                        last_error = f"{model} moderation blocked"
                        continue  # Try next model

                    # Other errors - try next model
                    self._parent.logger.warning(f"Video extension failed with {model}: {combined_output}")
                    last_error = combined_output
                    continue

                # Success!
                self._parent.logger.info(f"Video extension successful with {model}")

                # Get the new duration
                video = VideoFileClip(input_file)
                new_duration = video.duration
                video.close()

                return new_duration

            except (VideoTooLongForExtend, VideoTooShortForExtend):
                # Re-raise these immediately, don't try other models
                raise
            except Exception as e:
                self._parent.logger.error(f"Error extending video with {model}: {e}")
                last_error = str(e)
                continue

        # Both models failed
        error_msg = f"Video extension failed with all models. Last error: {last_error}"
        self._parent.logger.error(f"VIDEO EXTENSION FAILED: {error_msg}")
        raise VideoExtensionFailed()

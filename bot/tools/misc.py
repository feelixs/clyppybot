import logging
import traceback
from interactions import Message
import os
import subprocess
import concurrent.futures
import asyncio
from bot.kick import KickClip
from bot.twitch import TwitchClip
from typing import Optional, Union
from bot.errors import FailedTrim, FailureHandled
from dataclasses import dataclass


POSSIBLE_TOO_LARGE = ["trim", "info", "dm"]
POSSIBLE_ON_ERRORS = ["info", "dm"]

SUPPORT_SERVER_URL = "https://discord.gg/Xts5YMUbeS"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1111723928604381314&permissions=182272&scope=bot%20applications.commands"
TOPGG_VOTE_LINK = "https://top.gg/bot/1111723928604381314/vote"


@dataclass
class GuildType:
    id: int
    name: str


def create_nexus_str():
    return f"\n\n**[Invite CLYPPY]({INVITE_LINK}) | [Suggest a Feature]({SUPPORT_SERVER_URL}) | [Vote for me!]({TOPGG_VOTE_LINK})**"


class DownloadManager:
    def __init__(self, p):
        self._parent = p
        max_concurrent = os.getenv('MAX_RUNNING_AUTOEMBED_DOWNLOADS', 5)
        self._semaphore = asyncio.Semaphore(int(max_concurrent))

    async def download_clip(self, clip: Union[KickClip, TwitchClip], root_msg: Message, guild_ctx: GuildType) -> (Union[KickClip, TwitchClip], int):
        async with self._semaphore:
            if not isinstance(clip, Union[KickClip, TwitchClip]):
                self._parent.logger.error(f"Invalid clip object passed to download_clip of type {type(clip)}")
                return None, 0

            # Download clip
            f = await clip.download(autocompress=[guild_ctx.id == 759798762171662399])
            if not f:
                return None, 0

            # Check file size
            size_mb = os.path.getsize(f) / (1024 * 1024)
            if size_mb > 25:
                # Get guild setting for handling large files
                too_large_setting = self._parent.bot.guild_settings.get_too_large(guild_ctx.id).setting_str

                if too_large_setting == "trim":
                    # Calculate target duration and trim
                    target_duration = await self._parent.bot.tools.calculate_target_duration(f, target_size_mb=24.9)
                    if not target_duration:
                        self._parent.logger.error("First target_duration() failed")
                        raise FailedTrim
                    trimmed_file = await self._parent.bot.tools.trim_to_duration(f, target_duration)
                    if trimmed_file is None:
                        self._parent.logger.error("First trim_to_duration() failed")
                        raise FailedTrim
                    self._parent.logger.info(f"trimmed {clip.id} to {os.path.getsize(trimmed_file) / (1024 * 1024)}")

                    # second pass if necessary
                    if os.path.getsize(trimmed_file) / (1024 * 1024) > 25:
                        target_duration = await self._parent.bot.tools.calculate_target_duration(f, target_size_mb=24.5)
                        if not target_duration:
                            self._parent.logger.error("Second target_duration() failed")
                            raise FailedTrim
                        trimmed_file = await self._parent.bot.tools.trim_to_duration(f, target_duration)
                        if trimmed_file is None:
                            raise FailedTrim
                        self._parent.logger.info(f"trimmed {clip.id} to {os.path.getsize(trimmed_file) / (1024 * 1024)}")
                    if trimmed_file is not None:
                        os.remove(f)  # remove original file
                        return trimmed_file, 1
                elif too_large_setting == "info":
                    await root_msg.channel.send(
                        f"Sorry, this clip is too large ({size_mb:.1f}MB) for Discord's 25MB limit. "
                        "Unable to upload the file."
                    )
                    raise FailureHandled
                elif too_large_setting == "dm":
                    self._parent.bot.tools.send_dm_err_msg(f"Sorry, this clip is too large ({size_mb:.1f}MB) "
                                                           f"for Discord's 25MB limit. Unable to upload the file.")
                    raise FailureHandled
                raise Exception(f"Unhandled Exception in {__name__}")
            return f, 0


class Tools:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def send_dm_err_msg(self, ctx, guild, content):
        try:
            await ctx.author.send(f"{content}\n\n"
                                  f"This error occurred while trying to embed the clip in {guild.name}")
        except:
            self.logger.info(f"Failed to send DM to {ctx.author.name} ({ctx.author.id})\n{traceback.format_exc()}")

    async def calculate_target_duration(self, filepath, target_size_mb=25):
        # Get current size in MB
        current_size_mb = os.path.getsize(filepath) / (1024 * 1024)

        # Get video duration using ffprobe
        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = await loop.run_in_executor(
                    pool,
                    lambda: subprocess.run([
                        'ffprobe',
                        '-v', 'error',
                        '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1',
                        filepath
                    ], capture_output=True, text=True)
                )

            if result.returncode != 0:
                return None

            current_duration_sec = float(result.stdout.strip())  # Added strip()
        except (ValueError, subprocess.SubprocessError) as e:
            self.logger.error(f"Error getting duration: {e}")
            return None

        # Calculate target duration
        mb_per_second = current_size_mb / current_duration_sec
        self.logger.info(
            f"Current size: {current_size_mb} MB, duration: {current_duration_sec} seconds, speed: {mb_per_second} MB/s")
        target_duration = target_size_mb / mb_per_second
        self.logger.info(f"Target duration: {target_duration} seconds")

        return target_duration

    async def trim_to_duration(self, input_file: str, target_duration: float) -> Optional[str]:
        """
        Trims video to target duration using ffmpeg
        Returns path to trimmed file or None if failed
        """
        output_file = input_file.replace('.mp4', '_trimmed.mp4')
        self.logger.info(f"Trimming {input_file}...")
        try:
            # Use ffmpeg to trim without re-encoding (-c copy)
            command = [
                'ffmpeg',
                '-i', input_file,
                '-t', str(target_duration),  # Duration to trim to
                '-c', 'copy',  # Copy streams without re-encoding
                '-y',  # Overwrite output if exists
                output_file
            ]

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await process.communicate()

            if process.returncode != 0:
                self.logger.error("Failed to trim video")
                return None

            return output_file

        except Exception as e:
            self.logger.error(f"Error trimming video: {e}")
            return None

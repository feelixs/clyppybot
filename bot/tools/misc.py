import logging
import traceback
from interactions import Message
import os
import subprocess
import concurrent.futures
import asyncio
from bot.classes import BaseClip
from bot.kick import KickClip
from bot.twitch import TwitchClip
from bot.medal import MedalClip
from bot.reddit import RedditClip
from typing import Optional, Union
from bot.errors import FailedTrim, FailureHandled
from dataclasses import dataclass

POSSIBLE_TOO_LARGE = ["trim", "info", "dm"]
POSSIBLE_ON_ERRORS = ["dm", "info"]
POSSIBLE_EMBED_BUTTONS = ["all", "view", "dl", "none"]

SUPPORT_SERVER_URL = "https://discord.gg/Xts5YMUbeS"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1111723928604381314&permissions=182272&scope=bot%20applications.commands"
TOPGG_VOTE_LINK = "https://top.gg/bot/1111723928604381314/vote"


def tryremove(f):
    try:
        os.remove(f)
    except:
        pass


@dataclass
class GuildType:
    id: int
    name: str


def create_nexus_str():
    return f"\n\n**[Invite Clyppy]({INVITE_LINK}) | [Suggest a Feature]({SUPPORT_SERVER_URL}) | [Vote for me!]({TOPGG_VOTE_LINK})**"


class DownloadManager:
    def __init__(self, p):
        self._parent = p
        max_concurrent = os.getenv('MAX_RUNNING_AUTOEMBED_DOWNLOADS', 5)
        self._semaphore = asyncio.Semaphore(int(max_concurrent))

    async def download_clip(self, clip: BaseClip, root_msg: Message, guild_ctx: GuildType, too_large_setting=None) -> (Union[MedalClip, KickClip, TwitchClip], int):
        """Download and trim to 25MB"""
        async with self._semaphore:
            if not isinstance(clip, BaseClip):
                self._parent.logger.error(f"Invalid clip object passed to download_clip of type {type(clip)}")
                return None, 0

            was_edited = 0
            # check for existing clip file
            filename = f'clyppy_{clip.service}_{clip.id}.mp4'
            file_variants = [
                filename,
                filename.replace(".mp4", "_trimmed.mp4"),
                filename.replace(".mp4", "_trimmed2.mp4"),
                filename.replace(".mp4", "_trimmed3.mp4")
            ]
            f = None
            for variant in file_variants:
                if os.path.isfile(variant):
                    self._parent.logger.info(f"{variant} already exists, no need to download")
                    if os.path.getsize(variant) == 0:  # check for corrupt file
                        tryremove(variant)
                        self._parent.logger.info(f"{variant} was corrupt, so we are downloading and overwriting it")
                    else:
                        f, was_edited = variant, 1
                        if variant == filename:
                            was_edited = 0
                    break
            if f is None:
                # Download clip
                self._parent.logger.info("Run clip.download()")
                f = await clip.download(filename=filename)
                if not f:
                    return None, 0

            # Check file size
            size_mb = os.path.getsize(f) / (1024 * 1024)
            if size_mb > 25:
                if too_large_setting == "trim":
                    # Calculate target duration and trim
                    target_duration = await self._parent.calculate_target_duration(f, target_size_mb=24.9)
                    if not target_duration:
                        self._parent.logger.error("First target_duration() failed")
                        raise FailedTrim
                    trimmed_file = await self._parent.trim_to_duration(f, target_duration)
                    if trimmed_file is None:
                        self._parent.logger.error("First trim_to_duration() failed")
                        raise FailedTrim
                    self._parent.logger.info(f"trimmed {clip.id} to {round(os.path.getsize(trimmed_file) / (1024 * 1024), 1)}MB")
                    if os.path.getsize(trimmed_file) / (1024 * 1024) <= 25:
                        self._parent.logger.info("Deleting original file...")
                        tryremove(f)  # remove original file
                        return trimmed_file, 1

                    # second pass is necessary
                    second_target_duration = await self._parent.calculate_target_duration(f, target_size_mb=24)
                    if not second_target_duration:
                        self._parent.logger.error("Second target_duration() failed")
                        raise FailedTrim
                    second_trimmed_file = await self._parent.trim_to_duration(f, second_target_duration, append="_trimmed2")
                    if second_trimmed_file is None:
                        self._parent.logger.error("Second trim_to_duration() failed")
                        raise FailedTrim
                    self._parent.logger.info(f"(second pass) trimmed {clip.id} to "
                                             f"{round(os.path.getsize(second_trimmed_file) / (1024 * 1024), 1)}MB")
                    if os.path.getsize(second_trimmed_file) / (1024 * 1024) <= 25:
                        self._parent.logger.info("Deleting both original files...\n"
                                                 f"({f}, {trimmed_file}"
                                                 f"\nAnd returning {second_trimmed_file}")
                        tryremove(f)
                        tryremove(trimmed_file)  # remove original files
                        return second_trimmed_file, 1

                    # third pass is necessary
                    target_duration = await self._parent.calculate_target_duration(f, target_size_mb=20)
                    if not target_duration:
                        self._parent.logger.error("Third target_duration() failed")
                        raise FailedTrim
                    third_trimmed_file = await self._parent.trim_to_duration(f, target_duration, append="_trimmed3")
                    if third_trimmed_file is None:
                        self._parent.logger.error("Third trim_to_duration() failed")
                        raise FailedTrim
                    self._parent.logger.info(f"(third pass) trimmed {clip.id} to {round(os.path.getsize(third_trimmed_file) / (1024 * 1024), 1)}MB")
                    if os.path.getsize(third_trimmed_file) / (1024 * 1024) <= 25:
                        self._parent.logger.info("Deleting original file...")
                        tryremove(f)
                        tryremove(trimmed_file)
                        tryremove(second_trimmed_file)  # remove original files
                        return third_trimmed_file, 1

                elif too_large_setting == "info":
                    await root_msg.reply(
                        f"Sorry, this clip is too large ({size_mb:.1f}MB) for Discord's 25MB limit. "
                        "Unable to upload the file.\n\nYou can either:\n"
                        f" - upload a shorter clip\n"
                        f" - ask a server admin to change Clyppy "
                        f"settings to `too_large='trim'`\n"
                        f" - DM me the link and I'll"
                        f" upload a trimmed version"
                    )
                    raise FailureHandled
                elif too_large_setting == "dm":
                    await self._parent.send_dm_err_msg(ctx=root_msg, guild=guild_ctx,
                                                                 content=f"Sorry, the clip {clip.url} is too large "
                                                                         f"({size_mb:.1f}MB) for Discord's 25MB "
                                                                         f"limit. Unable to upload the file.\n\n"
                                                                         f"Please either\n"
                                                                         f" - upload a shorter clip\n"
                                                                         f" - ask a server admin to change Clyppy "
                                                                         f"settings to `too_large='trim'`\n"
                                                                         f" - resend the link in this DM and I'll"
                                                                         f" upload a trimmed version")
                    raise FailureHandled
                else:
                    self._parent.logger.info(f"Unhandled value for too_large_setting: {too_large_setting}")
                    await root_msg.reply(f"Your server's settings were out of whack!\n\n"
                                         f"For `too_large` got: '{too_large_setting}'\n"
                                         f"Expected: {POSSIBLE_TOO_LARGE}")
                    raise FailureHandled
                raise Exception(f"Unhandled Exception in bot.tools.misc")
            return f, was_edited


class Tools:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.dl = DownloadManager(self)

    async def send_error_message(self, msg_embed, dm_content, guild, ctx, bot, delete_after_on_reply=None):
        err = ""
        if bot.guild_settings.is_dm_on_error(guild.id):
            await self.send_dm_err_msg(ctx, guild, dm_content)
            return

        if error_channel_id := bot.guild_settings.get_error_channel(guild.id):
            if error_channel := bot.get_channel(error_channel_id):
                try:
                    await error_channel.send(embed=msg_embed)
                    return
                except Exception as e:
                    err += f"An error occurred when trying to message the channel <#{error_channel_id}>\n"
                    self.logger.warning(f"Cannot send to error channel {error_channel_id} in guild {guild.id}: {e}")
            else:
                err += (f"Could not find the channel <#{error_channel_id}>. "
                        f"Please reset the `error_channel` with `/setup`\n")

        await ctx.reply(err, embed=msg_embed, delete_after=delete_after_on_reply)

    async def send_dm_err_msg(self, ctx, guild, content):
        try:
            await ctx.author.send(f"{content}\n\n"
                                  f"This error occurred while trying to embed the clip in {guild.name}. "
                                  f"You're receiving this message because that server has the 'dm' setting "
                                  f"enabled for one of its `/settings`")
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

    async def trim_to_duration(self, input_file: str, target_duration: float, append=None) -> Optional[str]:
        """
        Trims video to target duration using ffmpeg
        Returns path to trimmed file or None if failed
        """
        if append is None:
            append = "_trimmed"
        output_file = input_file.replace('.mp4', f'{append}.mp4')
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

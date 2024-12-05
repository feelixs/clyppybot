import traceback
import interactions.api.events
from interactions import Extension, Message, Embed, Permissions, listen, Button, ButtonStyle
from interactions.api.events import MessageCreate
from bot.tools import create_nexus_str
from typing import List
from bot.tools import DownloadManager, GuildType
from bot.errors import FailedTrim, FailureHandled
import os
import re
import logging


class KickAutoEmbed(Extension):
    def __init__(self, bot):
        self.logger = logging.getLogger(__name__)
        self.bot = bot
        self.too_large_clips = []
        self._dl = DownloadManager(self)

    @listen(MessageCreate)
    async def on_message_create(self, event: MessageCreate):
        try:
            if event.message.guild is None:
                # if we're in dm context, set the guild id to the author id
                guild = GuildType(event.message.author.id, event.message.author.username)
            else:
                guild = GuildType(event.message.guild.id, event.message.guild.name)
                # if we're in guild ctx, we need to verify clyppy has the right perms
                if Permissions.ATTACH_FILES not in event.message.channel.permissions_for(event.message.guild.me):
                    return 1
                if Permissions.SEND_MESSAGES not in event.message.channel.permissions_for(event.message.guild.me):
                    return 1
            if event.message.author.id == self.bot.user.id:
                return 1  # don't respond to the bot's own messages

            words = self._getwords(event.message.content)
            num_links = self._get_num_clip_links(words)
            if num_links == 1:
                contains_clip_link, index = self._get_next_clip_link_loc(words, 0)
                if not contains_clip_link:
                    return 1
                await self._process_this_clip_link(words[index], event.message, guild)
            elif num_links > 1:
                next_link_exists = True
                index = -1  # we will +1 in the next step (setting it to 0 for the start)
                while next_link_exists:
                    next_link_exists, index = self._get_next_clip_link_loc(words, index + 1)
                    if not next_link_exists:
                        return 1
                    await event.message.reply(f"Processing link: {words[index]}", delete_after=10)
                    await self._process_this_clip_link(words[index], event.message, guild, True)
        except Exception as e:
            self.logger.info(f"Error in AutoEmbed on_message_create: {event.message.content}\n{traceback.format_exc()}")

    @staticmethod
    def _getwords(text: str) -> List[str]:
        return re.split(r"[ \n]+", text)

    def _get_next_clip_link_loc(self, words: List[str], n=0) -> (bool, int):
        for i in range(n, len(words)):
            word = words[i]
            if self.bot.kick.is_kick_clip_link(word):
                self.logger.info(f"Found clip link: {word}")
                return True, i
        return False, 0

    def _get_num_clip_links(self, words: List[str]):
        n = 0
        for word in words:
            if self.bot.kick.is_kick_clip_link(word):
                n += 1
        return n

    async def _process_this_clip_link(self, clip_link: str, respond_to: Message, guild: GuildType, include_link=False):
        async def handle_error(title: str, description: str, log_msg: str = None):
            self.logger.info(log_msg or description)
            if self.bot.guild_settings.get_on_error(guild.id) == "dm":
                await self.bot.tools.send_dm_err_msg(respond_to, guild, description)
            else:
                emb = Embed(title=title, description=f"{description}\n{create_nexus_str()}")
                await respond_to.reply(embed=emb, delete_after=60 if "try linking it again" in description else None)
            return 1

        # Check if clip was previously too large
        parsed_id = self.bot.kick.parse_clip_url(clip_link)
        if parsed_id in self.too_large_clips:
            return await handle_error(
                "**Whoops...**",
                f"Looks like the video embed failed this clip:\n{clip_link}\n\nTry linking a shorter clip!\n"
                "This clip file was previously reported as too large to fit Discord's limit.",
                f"Skipping quick embed for clip {parsed_id} in {guild.name}, clip was previously reported too large"
            )

        # Get clip info
        clip = await self.bot.kick.get_clip(clip_link)
        if clip is None:
            return await handle_error(
                "**Invalid Clip Link**",
                f"Looks like the Kick clip `{clip_link}` couldn't be downloaded. Verify that it exists",
                f"Failed to download clip: **Invalid Clip Link** {clip_link}"
            )

        # Download clip
        try:
            clip_file, edited = await self._dl.download_clip(clip, root_msg=respond_to, guild_ctx=guild)
            if clip_file is None:
                raise Exception("Download returned None")
            return clip_file, edited

        except FailedTrim:
            return await handle_error(
                "**Whoops...**",
                "I failed to trim that video file. If this keeps on happening, you should probably let us know...\n"
                "> The original file size was larger than Discord's Limit for Bots, **25MB**. I tried to trim it to fit, but failed.",
                f"Clip {clip.id} failed to trim :/"
            )

        except FailureHandled:
            self.logger.info("Failed to download clip, dm/info triggered")
            return 1

        except Exception as e:
            return await handle_error(
                "**Oops...**",
                f"I messed up while trying to download this clip: \n\n{clip_link}\n"
                "Please try linking it again.\n"
                "If the issue keeps on happening, please contact us on our support server.",
                f"Unhandled exception in download: {traceback.format_exc()}"
            )

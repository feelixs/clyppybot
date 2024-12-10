from interactions import Permissions, Embed, Message, Button, ButtonStyle
from interactions import errors
from interactions.api.events import MessageCreate
from bot.tools import DownloadManager, GuildType
from bot.tools import create_nexus_str
from bot.errors import FailedTrim, FailureHandled
from typing import List
import traceback
import re
import os


class AutoEmbedder:
    def __init__(self, bot, platform_tools, logger):
        self.bot = bot
        self.too_large_clips = []
        self._dl = DownloadManager(self)
        self.logger = logger
        self.platform_tools = platform_tools

    @staticmethod
    def _getwords(text: str) -> List[str]:
        return re.split(r"[ \n]+", text)

    def _get_next_clip_link_loc(self, words: List[str], n=0) -> (bool, int):
        for i in range(n, len(words)):
            word = words[i]
            if self.platform_tools.is_clip_link(word):
                self.logger.info(f"Found clip link: {word}")
                return True, i
        return False, 0

    def _get_num_clip_links(self, words: List[str]):
        n = 0
        for word in words:
            if self.platform_tools.is_clip_link(word):
                n += 1
        return n

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

    async def _process_this_clip_link(self, clip_link: str, respond_to: Message, guild: GuildType, include_link=False) -> None:
        parsed_id = self.platform_tools.parse_clip_url(clip_link)
        if parsed_id in self.too_large_clips and not self.bot.guild_settings.is_trim_enabled(guild.id):
            self.logger.info(f"Skipping quick embed for clip {parsed_id} in {guild.name}, clip was previously reported too large")
            if self.bot.guild_settings.is_dm_on_error(guild.id):
                await self.bot.tools.send_dm_err_msg(respond_to,  f"The clip {clip_link} was previously reported as too large to fit Discord's limit.\n\n"
                                                                  f"You can either:"
                                                                  f" - upload a shorter clip\n"
                                                                  f" - ask a server admin to change CLYPPY "
                                                                  f"settings to `too_large='trim'`\n"
                                                                  f" - resend the link in this DM and I'll"
                                                                  f" upload a trimmed version"
                                                     )
                return
            emb = Embed(title="**Whoops...**",
                        description=f"Looks like the video embed failed this clip as it was too large:\n{clip_link}\n\n "
                                    f"Either: link a shorter clip, ask an admin to enable `too_large='trim'` "
                                    f"using /settings, or DM me the link and I'll trim it for you.")
            emb.description += create_nexus_str()
            await respond_to.reply(embed=emb)
            return

        clip = await self.platform_tools.get_clip(clip_link)
        if clip is None:
            self.logger.info(f"Failed to download clip: **Invalid Clip Link** {clip_link}")
            if self.bot.guild_settings.is_dm_on_error(guild.id):
                await self.bot.tools.send_dm_err_msg(respond_to, f"Failed to download clip: **Invalid Clip Link** {clip_link}")
                return
            emb = Embed(title="**Invalid Clip Link**",
                        description=f"Looks like the clip `{clip_link}` couldn't be downloaded. Verify that it exists")
            emb.description += create_nexus_str()
            await respond_to.reply(embed=emb)
            return

        # download clip video
        try:
            clip_file, edited = await self._dl.download_clip(clip, root_msg=respond_to, guild_ctx=guild)

            if clip_file is None:
                self.logger.info(f"Failed to download clip {clip_link}: {traceback.format_exc()}")
                if self.bot.guild_settings.is_dm_on_error(guild.id):
                    await self.bot.tools.send_dm_err_msg(respond_to, guild, f"Failed to download clip {clip_link}")
                    return
                emb = Embed(title="**Invalid Clip Link**",
                            description=f"Looks like the clip `{clip_link}` couldn't be downloaded. Verify that it exists")
                emb.description += create_nexus_str()
                await respond_to.reply(embed=emb, delete_after=60)
                return

        except FailedTrim:
            self.logger.info(f"Clip {clip.id} failed to trim :/")
            if self.bot.guild_settings.is_dm_on_error(guild.id):
                await self.bot.tools.send_dm_err_msg(respond_to, guild,
                                                     f"The clip `{clip_link}` was too large to upload to Discord, "
                                                     f"and I failed to properly trim the video from it.")
                return
            emb = Embed(title="**Whoops...**",
                        description=f"I failed to trim that video file. If this keeps on happening, you should probably let us know...\n"
                                    f"> The original file size was larger than Discord's Limit for Bots, **25MB**. I tried to trim it to fit, but failed.")
            emb.description += create_nexus_str()
            await respond_to.reply(embed=emb)
            return
        except FailureHandled:
            self.logger.info("Failed to download clip, dm/info triggered")
            return
        except:
            self.logger.info(f"Unhandled exception in download - notifying: {traceback.format_exc()}")
            if self.bot.guild_settings.is_dm_on_error(guild.id):
                await self.bot.tools.send_dm_err_msg(respond_to, guild, f"Failed to download clip {clip_link}")
                return
            emb = Embed(title="**Oops...**",
                        description=f"I messed up while trying to download this clip: "
                                    f"\n\n{clip_link}\nPlease try linking it again.\n"
                                    "If the issue keeps on happening, please contact us on our support server.")
            emb.description += create_nexus_str()
            await respond_to.reply(embed=emb, delete_after=60)
            return

        # send video file
        try:
            if not edited:
                comp = Button(style=ButtonStyle.LINK, label=f"View On {self.platform_tools.platform_name}", url=clip.url)
            else:
                comp = Button(style=ButtonStyle.LINK, label="Trimmed - View Full Clip", url=clip.url)
            if include_link:
                await respond_to.reply(clip.url, file=clip_file, components=[comp])
            else:
                await respond_to.reply(file=clip_file, components=[comp])

        except errors.HTTPException as e:
            if e.status == 413:  # Check the error source for 413 (file too large)
                self.too_large_clips.append(clip.id)
                clipsize = os.stat(clip_file).st_size
                self.logger.info(f"Clip {clip.id} was too large to embed in {guild.name}")
                if self.bot.guild_settings.is_dm_on_error(guild.id):
                    await self.bot.tools.send_dm_err_msg(respond_to, guild,
                                                         f"The clip {clip_link} was too large to embed in {guild.name} "
                                                         f"({round(clipsize / (1024 * 1024), 1)}MB, Discord's Limit is 25MB)")
                    return
                emb = Embed(title="**Whoops...**",
                            description=f"Looks like the video embed failed for:\n{clip_link} \n\nYou should probably report this error to us\n"
                                        f"> File size was **{round(clipsize / (1024 * 1024), 1)}MB**, while Discord's Limit for Bots is **25MB**")
                emb.description += create_nexus_str()
                await respond_to.reply(embed=emb)
                return
            else:
                self.logger.info(f"Unknown HTTPException in _process_this_clip_link: {traceback.format_exc()}")
                if self.bot.guild_settings.is_dm_on_error(guild.id):
                    await self.bot.tools.send_dm_err_msg(respond_to, guild, f"Failed to download clip {clip_link}")
                    return
                emb = Embed(title="**Oops...**",
                            description=f"I messed up while trying to download this clip:\n{clip_link} "
                                        f"\n\nPlease try linking it again.\n"
                                        "If the issue keeps on happening, please contact us on our support server.")
                emb.description += create_nexus_str()
                await respond_to.reply(embed=emb, delete_after=60)
                return
        except Exception:
            self.logger.info(f"Unknown Exception in _process_this_clip_link: {traceback.format_exc()}")
            if self.bot.guild_settings.is_dm_on_error(guild.id):
                await self.bot.tools.send_dm_err_msg(respond_to, guild, f"Failed to download clip {clip_link}")
                return
            emb = Embed(title="**Oops...**",
                        description=f"I messed up while trying to download this clip:\n{clip_link} "
                                    f"\n\nPlease try linking it again.\n"
                                    "If the issue keeps on happening, please contact us on our support server.")
            emb.description += create_nexus_str()
            await respond_to.reply(embed=emb, delete_after=60)
            return
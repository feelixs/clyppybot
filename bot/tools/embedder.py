from interactions import Permissions, Embed, Message, Button, ButtonStyle
from interactions import errors
from interactions.api.events import MessageCreate
from bot.tools import GuildType
from bot.tools import create_nexus_str
from bot.errors import FailedTrim, FailureHandled
from datetime import datetime, timezone
from typing import List
import traceback
import aiohttp
import time
import re
import os
import asyncio
from bot.classes import TARGET_SIZE_MB


VALID_DL_PLATFORMS = ['twitch', 'medal']


async def publish_interaction(interaction_data, apikey):
    url = 'https://clyppy.io/api/publish/'
    headers = {
        'X-API-Key': apikey,
        'Content-Type': 'application/json'
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=interaction_data, headers=headers) as response:
            if response.status == 201:  # Successfully created
                return await response.json()
            else:
                error_data = await response.json()
                raise Exception(f"Failed to publish interaction: {error_data.get('error', 'Unknown error')}")


class AutoEmbedder:
    def __init__(self, bot, platform_tools, logger):
        self.api_key = os.getenv('clyppy_post_key')
        self.bot = bot
        self.too_large_clips = []
        self.logger = logger
        self.platform_tools = platform_tools
        self.silence_invalid_url = self.platform_tools.silence_invalid_url
        self.currently_downloading = []

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
                guild = GuildType(event.message.author.id, event.message.author.username, True)
            else:
                guild = GuildType(event.message.guild.id, event.message.guild.name, False)
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
                await self._process_clip_one_at_a_time(words[index], event.message, guild)
            elif num_links > 1:
                next_link_exists = True
                index = -1  # we will +1 in the next step (setting it to 0 for the start)
                while next_link_exists:
                    next_link_exists, index = self._get_next_clip_link_loc(words, index + 1)
                    if not next_link_exists:
                        return 1
                    await event.message.reply(f"Processing link: {words[index]}", delete_after=10)
                    await self._process_clip_one_at_a_time(words[index], event.message, guild, True)
        except Exception as e:
            self.logger.info(f"Error in AutoEmbed on_message_create: {event.message.content}\n{traceback.format_exc()}")

    async def _process_clip_one_at_a_time(self, clip_link: str, respond_to: Message, guild: GuildType, include_link=False):
        parsed_id = self.platform_tools.parse_clip_url(clip_link)
        if parsed_id in self.currently_downloading:
            await self._wait_for_download(parsed_id)
        else:
            self.currently_downloading.append(parsed_id)
        try:
            await self._process_this_clip_link(parsed_id, clip_link, respond_to, guild, include_link)
        except Exception as e:
            print(f"Error in processing this clip link one at a time: {clip_link} - {e}")
        finally:
            try:
                self.currently_downloading.remove(parsed_id)
            except ValueError:
                pass

    async def _wait_for_download(self, clip_id: str, timeout: float = 30):
        start_time = time.time()
        while clip_id in self.currently_downloading:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Waiting for clip {clip_id} download timed out")
            await asyncio.sleep(0.1)

    async def _process_this_clip_link(self, parsed_id: str, clip_link: str, respond_to: Message, guild: GuildType, include_link=False) -> None:
        if parsed_id in self.too_large_clips and not self.bot.guild_settings.is_trim_enabled(guild.id):
            self.logger.info(f"Skipping quick embed for clip {parsed_id} in {guild.name}, clip was previously reported too large")
            emb = Embed(title="**Whoops...**",
                        description=f"Looks like the video embed failed this clip as it was too large:\n{clip_link}\n\n"
                                    f" Either: link a shorter clip, ask an admin to enable `too_large='trim'` "
                                    f"using /settings, or DM me the link and I'll trim it for you.")
            emb.description += create_nexus_str()
            await self.bot.tools.send_error_message(
                ctx=respond_to,
                msg_embed=emb,
                dm_content=f"The clip {clip_link} was previously reported as too large to fit Discord's limit.\n\n"
                           f"You can either:\n - upload a shorter clip\n - ask a server admin to change Clyppy "
                           f"settings to `too_large='trim'`"
                           f"\n - resend the link in this DM and I'll upload a trimmed version",
                bot=self.bot,
                guild=guild
            )
            return

        clip = await self.platform_tools.get_clip(clip_link)
        if clip is None:
            if not self.silence_invalid_url:
                self.logger.info(f"Failed to download clip: **Invalid Clip Link** {clip_link}")
                emb = Embed(title="**Invalid Clip Link**",
                            description=f"Looks like the clip `{clip_link}` couldn't be downloaded. Verify that it exists")
                emb.description += create_nexus_str()
                await self.bot.tools.send_error_message(
                    ctx=respond_to,
                    msg_embed=emb,
                    dm_content=f"Failed to download clip: **Invalid Clip Link** {clip_link}",
                    bot=self.bot,
                    guild=guild
                )
            return

        # download clip video
        try:
            clip_file, edited = await self.bot.tools.dl.download_clip(
                clip=clip,
                root_msg=respond_to,
                guild_ctx=guild,
                too_large_setting=str(self.bot.guild_settings.get_too_large(guild.id))
            )

            if clip_file is None:
                if not self.silence_invalid_url:
                    self.logger.info(f"Failed to download clip {clip_link}: {traceback.format_exc()}")
                    emb = Embed(title="**Invalid Clip Link**",
                                description=f"Looks like the clip `{clip_link}` couldn't be downloaded. Verify that it exists")
                    emb.description += create_nexus_str()
                    await self.bot.tools.send_error_message(
                        ctx=respond_to,
                        msg_embed=emb,
                        dm_content=f"Failed to download clip {clip_link}",
                        bot=self.bot,
                        guild=guild,
                        delete_after_on_reply=60
                    )
                return

        except FailedTrim:
            self.logger.info(f"Clip {clip.id} failed to trim :/")
            emb = Embed(title="**Whoops...**",
                        description=f"I failed to trim that video file. If this keeps on happening, you should probably let us know...\n"
                                    f"> The original file size was larger than Discord's Limit for Bots, *{TARGET_SIZE_MB}MB**. I tried to trim it to fit, but failed.")
            emb.description += create_nexus_str()
            await self.bot.tools.send_error_message(
                ctx=respond_to,
                msg_embed=emb,
                dm_content=f"The clip `{clip_link}` was too large to upload to Discord, and I failed to properly trim the video from it.",
                bot=self.bot,
                guild=guild
            )
            return
        except FailureHandled:
            self.logger.info("Failed to download clip, dm/info triggered")
            return
        except:
            self.logger.info(f"Unhandled exception in download - notifying: {traceback.format_exc()}")
            emb = Embed(title="**Oops...**",
                        description=f"I messed up while trying to download this clip: "
                                    f"\n\n{clip_link}\nPlease try linking it again.\n"
                                    "If the issue keeps on happening, please contact us on our support server.")
            emb.description += create_nexus_str()
            await self.bot.tools.send_error_message(
                ctx=respond_to,
                msg_embed=emb,
                dm_content=f"Failed to download clip {clip_link}",
                bot=self.bot,
                guild=guild,
                delete_after_on_reply=60
            )
            return

        # send video file
        try:
            comp = []
            # refer to: ["all", "view", "dl", "none"]
            btn_idx = self.bot.guild_settings.get_embed_buttons(guild.id)
            if btn_idx <= 1:
                if not edited:
                    txt = f"View On {self.platform_tools.platform_name}"
                else:
                    txt = "Trimmed - View Full Clip"
                comp.append(Button(style=ButtonStyle.LINK, label=txt, url=clip.url))
            if (btn_idx == 0 or btn_idx == 2) and self.platform_tools.platform_name.lower() in VALID_DL_PLATFORMS:
                if not edited:
                    txt = "Download"
                else:
                    txt = "Download Full Clip"
                comp.append(Button(
                    style=ButtonStyle.LINK,
                    label=txt,
                    url=f"https://clyppy.io/clip-downloader?clip={clip.url}"
                ))
            if include_link:
                await respond_to.reply(clip.url, file=clip_file, components=comp)
            else:
                await respond_to.reply(file=clip_file, components=comp)
                
            now_utc = datetime.now(tz=timezone.utc).timestamp()
            respond_to_utc = respond_to.timestamp.astimezone(tz=timezone.utc).timestamp()
            my_response_time = round((now_utc - respond_to_utc), 2)
            self.logger.info(f"Successfully embedded clip {clip.id} in {guild.name} in {my_response_time} seconds")
            chn, chnid = None, None
            try:
                chn = respond_to.channel.name
                chnid = respond_to.channel.id
            except:
                pass
            if chn is None:
                chn = "dm"
                chnid = 0
            interaction_data = {
                'server_name': guild.name,
                'channel_name': chn,
                'user_name': respond_to.author.username,
                'server_id': str(guild.id),
                'channel_id': str(chnid),
                'user_id': str(respond_to.author.id),
                'embedded_url': clip_link,
                'remote_file_url': clip_link,  # todo
                'url_platform': self.platform_tools.platform_name,
                'response_time_seconds': my_response_time,
                'total_servers_now': len(self.bot.guilds)
            }

            try:
                result = await publish_interaction(interaction_data, apikey=self.api_key)
                # Handle success
            except Exception as e:
                # Handle error
                self.logger.info(f"Failed to post interaction to API: {e}")

        except errors.HTTPException as e:
            if e.status == 413:  # Check the error source for 413 (file too large)
                self.too_large_clips.append(clip.id)
                clipsize = os.stat(clip_file).st_size
                self.logger.info(f"Clip {clip.id} was too large to embed in {guild.name}")
                emb = Embed(title="**Whoops...**",
                            description=f"Looks like the video embed failed for:\n{clip_link} \n\nYou should probably report this error to us\n"
                                        f"> File size was **{round(clipsize / (1024 * 1024), 1)}MB**, while Discord's Limit for Bots is **{TARGET_SIZE_MB}MB**")
                emb.description += create_nexus_str()
                await self.bot.tools.send_error_message(
                    ctx=respond_to,
                    msg_embed=emb,
                    dm_content=f"The clip {clip_link} was too large to embed in {guild.name} "
                               f"({round(clipsize / (1024 * 1024), 1)}MB, Discord's Limit is {TARGET_SIZE_MB}MB)",
                    guild=guild,
                    bot=self.bot
                )
                return
            else:
                self.logger.info(f"Unknown HTTPException in _process_this_clip_link: {traceback.format_exc()}")
                emb = Embed(title="**Oops...**",
                            description=f"I messed up while trying to download this clip:\n{clip_link} "
                                        f"\n\nPlease try linking it again.\n"
                                        "If the issue keeps on happening, please contact us on our support server.")
                emb.description += create_nexus_str()
                await self.bot.tools.send_error_message(
                    ctx=respond_to,
                    msg_embed=emb,
                    dm_content=f"Failed to download clip {clip_link}",
                    guild=guild,
                    bot=self.bot,
                    delete_after_on_reply=60
                )
                return
        except Exception:
            self.logger.info(f"Unknown Exception in _process_this_clip_link: {traceback.format_exc()}")
            emb = Embed(title="**Oops...**",
                        description=f"I messed up while trying to download this clip:\n{clip_link} "
                                    f"\n\nPlease try linking it again.\n"
                                    "If the issue keeps on happening, please contact us on our support server.")
            emb.description += create_nexus_str()
            await self.bot.tools.send_error_message(
                ctx=respond_to,
                msg_embed=emb,
                dm_content=f"Failed to download clip {clip_link}",
                guild=guild,
                bot=self.bot,
                delete_after_on_reply=60
            )
            return

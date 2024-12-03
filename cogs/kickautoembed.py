import traceback
import interactions.api.events
from interactions import Extension, Message, Embed, Permissions, listen
from interactions.api.events import MessageCreate
from bot.kick import KickClip
from bot.errors import ClipNotExists, DriverDownloadFailed
from bot.tools import create_nexus_str
from typing import Union, List
import concurrent.futures
import asyncio
import os
import re
import logging


class KickAutoEmbed(Extension):
    def __init__(self, bot):
        self.logger = logging.getLogger(__name__)
        self.bot = bot
        self.too_large_clips = []
        self._dl = self.DownloadManager(self)

    class DownloadManager:
        def __init__(self, p):
            self._parent = p
            max_concurrent = os.getenv('MAX_RUNNING_AUTOEMBED_DOWNLOADS', 5)
            self._semaphore = asyncio.Semaphore(int(max_concurrent))

        async def download_clip(self, clip: Union[KickClip, str], root_msg: Message) -> Union[KickClip, int]:
            async with self._semaphore:
                f = None
                if isinstance(clip, KickClip):
                    loop = asyncio.get_event_loop()
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        f = await loop.run_in_executor(pool, clip.download, root_msg, [root_msg.guild.id == 759798762171662399])
                else:
                    self._parent.logger.error("Invalid clip object passed to download_clip of type %s" % type(clip))
                return f

    @listen(MessageCreate)
    async def on_message_create(self, event: MessageCreate):
        try:
            if Permissions.ATTACH_FILES not in event.message.channel.permissions_for(event.message.guild.me):
                # self.logger.info(f"Missing Attach Files permission in {event.message.guild.name} - {event.message.channel.name}, skipping quick embed")
                return 1
            if Permissions.SEND_MESSAGES not in event.message.channel.permissions_for(event.message.guild.me):
                self.logger.info(f"Missing Send Messages permission in {event.message.guild.name} - {event.message.channel.name}, skipping quick embed")
                return 1
            if event.message.author.id == self.bot.user.id:
                return 1  # don't respond to the bot's own messages

            words = self._getwords(event.message.content)
            # self.logger.info(f"{event.message.guild.name} - {event.message.channel.name}, Content: {event.message.content}, Words: {words}")
            num_links = self._get_num_clip_links(words)
            if num_links == 1:
                contains_clip_link, index = self._get_next_clip_link_loc(words, 0)
                if not contains_clip_link:
                    return 1
                await self._process_this_clip_link(words[index], event.message)
            elif num_links > 1:
                next_link_exists = True
                index = -1  # we will +1 in the next step (setting it to 0 for the start)
                while next_link_exists:
                    next_link_exists, index = self._get_next_clip_link_loc(words, index + 1)
                    if not next_link_exists:
                        return 1
                    await event.message.reply(f"Processing link: {words[index]}", delete_after=10)
                    await self._process_this_clip_link(words[index], event.message, True)
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

    async def _process_this_clip_link(self, clip_link: str, respond_to: Message, include_link=False):
        parsed_id = self.bot.kick.parse_clip_url(clip_link)
        if parsed_id in self.too_large_clips:
            emb = Embed(title="**Whoops...**",
                        description=f"Looks like the video embed failed this clip:\n{clip_link}\n\n "
                                    f"Try linking a shorter clip!\n"
                                    "This clip file was previously reported as too large to fit Discord's limit.")
            emb.description += create_nexus_str()
            await respond_to.reply(embed=emb)
            self.logger.info(
                f"Skipping quick embed for clip {parsed_id} in {respond_to.guild.name} - {respond_to.channel.name}, clip was previously reported too large")
            return 1

        clip = await self.bot.kick.get_clip(clip_link)
        if clip is None:
            emb = Embed(title="**Invalid Clip Link**",
                        description=f"Looks like the Kick clip `{clip_link}` couldn't be downloaded. Verify that it exists")
            emb.description += create_nexus_str()
            await respond_to.reply(embed=emb)
            return 1
        clip_file = await self._dl.download_clip(clip, root_msg=respond_to)
        if clip_file is None:
            self.logger.info(f"Failed to download clip {clip_link}: {traceback.format_exc()}")
            emb = Embed(title="**Oops...**",
                        description=f"I messed up while trying to download this clip: \n\n\
                                            {clip_link}\nPlease try linking it again.\n"
                                    "If the issue keeps on happening, please contact us on our support server.")
            emb.description += create_nexus_str()
            await respond_to.reply(embed=emb, delete_after=60)
            return 1
        try:
            if include_link:
                await respond_to.reply(clip_link, file=clip_file)
            else:
                await respond_to.reply(file=clip_file)
        except interactions.errors.HTTPException as e:
            if e.status == 413:  # Check the error source for 413 (file too large)
                clipsize = os.stat(clip_file).st_size
                emb = Embed(title="**Whoops...**",
                            description=f"Looks like the video embed failed for:\n{clip_link} \n\nTry linking a shorter clip!\n"
                                        f"> File size was **{round(clipsize / (1024 * 1024))}MB**, while Discord's Limit for Bots is **25MB**")
                emb.description += create_nexus_str()
                self.too_large_clips.append(clip.id)
                self.logger.info(f"Clip {clip.id} was too large to embed in {respond_to.guild.name} - {respond_to.channel.name}")
                await respond_to.reply(embed=emb)
                return 1
            else:
                self.logger.info(f"Unknown HTTPException in _process_this_clip_link: {traceback.format_exc()}")
                emb = Embed(title="**Oops...**",
                            description=f"I messed up while trying to download this clip:\n{clip_link} "
                                        f"\n\nPlease try linking it again.\n"
                                        "If the issue keeps on happening, please contact us on our support server.")
                emb.description += create_nexus_str()
                await respond_to.reply(embed=emb, delete_after=60)
                return 1
        except:
            self.logger.info(f"Unknown Exception in _process_this_clip_link: {traceback.format_exc()}")
            emb = Embed(title="**Oops...**",
                        description=f"I messed up while trying to download this clip:\n{clip_link} "
                                    f"\n\nPlease try linking it again.\n"
                                    "If the issue keeps on happening, please contact us on our support server.")
            emb.description += create_nexus_str()
            await respond_to.reply(embed=emb, delete_after=60)
            return 1

from interactions import Permissions, Embed, Message, Button, ButtonStyle, SlashContext, TYPE_THREAD_CHANNEL, ActionRow, errors
from bot.errors import VideoTooLong, NoDuration, ClipFailure, UnknownError
from bot.io import get_aiohttp_session, is_404
from datetime import datetime, timezone, timedelta
from interactions.api.events import MessageCreate
from bot.tools.misc import create_nexus_str
from bot.types import DownloadResponse, GuildType
from bot.classes import DL_SERVER_ID
from typing import List, Union
import traceback
import asyncio
import time
import re
import os


INVALID_DL_PLATFORMS = []


async def publish_interaction(interaction_data, apikey, edit_id=None, edit_type=None, logger=None):
    try:
        url = 'https://clyppy.io/api/publish/'
        headers = {
            'X-API-Key': apikey,
            'Content-Type': 'application/json'
        }
        if edit_type is None:
            # publish new interaction
            j = interaction_data
        elif edit_type == "response_time":
            if edit_id is None:
                raise Exception("both edit_id and edit_type must be defined, or both None")
            j = {'edit': True, 'id': edit_id, 'response_time_seconds': interaction_data}
        else:
            raise Exception("Invalid call to publish_interaction()")
        async with get_aiohttp_session() as session:
            async with session.post(url, json=j, headers=headers) as response:
                if response.status == 201:  # Successfully created
                    return await response.json()
                else:
                    error_data = await response.json()
                    logger.info(error_data)
                    raise Exception(f"Failed to publish interaction: {error_data.get('error', 'Unknown error')}")
    except:
        logger.info(traceback.format_exc())


class AutoEmbedder:
    def __init__(self, bot, platform_tools, logger):
        self.api_key = os.getenv('clyppy_post_key')
        self.bot = bot
        self.too_large_clips = []
        self.logger = logger
        self.platform_tools = platform_tools
        self.currently_downloading = []
        self._clip_id_msg_timestamps = {}

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
                if Permissions.EMBED_LINKS not in event.message.channel.permissions_for(event.message.guild.me):
                    return 1
                if Permissions.SEND_MESSAGES not in event.message.channel.permissions_for(event.message.guild.me):
                    return 1
                if Permissions.READ_MESSAGE_HISTORY not in event.message.channel.permissions_for(event.message.guild.me):
                    return 1
                if Permissions.SEND_MESSAGES_IN_THREADS not in event.message.channel.permissions_for(event.message.guild.me):
                    if isinstance(event.message.channel, TYPE_THREAD_CHANNEL):
                        return 1
                if not event.message.channel.nsfw and self.platform_tools.is_nsfw:
                    # only allow nsfw in nsfw channels
                    return 1

            if event.message.author.id == self.bot.user.id:
                return 1  # don't respond to the bot's own messages
            if not self.bot.guild_settings.get_embed_enabled(guild.id):
                return 1

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
                    await self._process_clip_one_at_a_time(words[index], event.message, guild, True)
        except Exception as e:
            self.logger.info(f"Error in AutoEmbed on_message_create: {event.message.content}\n{traceback.format_exc()}")

    async def _process_clip_one_at_a_time(self, clip_link: str, respond_to: Message, guild: GuildType, include_link=False):
        parsed_id = self.platform_tools.parse_clip_url(clip_link)
        self._clip_id_msg_timestamps[respond_to.id] = datetime.now().timestamp()
        if parsed_id in self.currently_downloading:
            await self._wait_for_download(parsed_id)
        else:
            self.currently_downloading.append(parsed_id)
        try:
            await self._process_this_clip_link(clip_link, respond_to, guild, include_link)
        except VideoTooLong:
            self.logger.info(f"VideoTooLong was reported for {clip_link}")
        except NoDuration:
            self.logger.info(f"NoDuration was reported for {clip_link}")
        except ClipFailure:
            self.logger.info(f"ClipFailure was reported for {clip_link}")
        except Exception as e:
            self.logger.info(f"Error in processing this clip link one at a time: {clip_link} - {e}")
        finally:
            try:
                self.currently_downloading.remove(parsed_id)
            except ValueError:
                pass
            try:
                del self._clip_id_msg_timestamps[respond_to.id]
            except:
                pass

    async def _wait_for_download(self, clip_id: str, timeout: float = 30):
        start_time = time.time()
        while clip_id in self.currently_downloading:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Waiting for clip {clip_id} download timed out")
            await asyncio.sleep(0.1)

    async def _process_this_clip_link(self, clip_link: str, respond_to: Union[Message, SlashContext], guild: GuildType, extended_url_formats=False, try_send_files=True) -> None:
        clip = await self.platform_tools.get_clip(clip_link, extended_url_formats=True, basemsg=respond_to)
        if guild.is_dm:  # dm gives error (nonetype has no attribute 'permissions_for')
            has_file_perms = True
        else:
            has_file_perms = Permissions.ATTACH_FILES in respond_to.channel.permissions_for(respond_to.guild.me)

        will_send_files = has_file_perms and try_send_files

        if clip is None:
            self.logger.info(f"Failed to fetch clip: **Invalid Clip Link** {clip_link}")
            # should silently fail
            return None
        # retrieve clip video url
        video_doesnt_exist, error_code = await is_404(clip.clyppy_url, self.logger)
        if str(guild.id) == str(DL_SERVER_ID) and isinstance(respond_to, Message):
            # if we're in video dl server -> StoredVideo obj for this clip probably already exists
            the_file = f'https://clyppy.io/media/clips/{clip.service}_{clip.clyppy_id}.mp4'
            file_exists, _ = await is_404(the_file)
            if file_exists:
                # we're assuming the StoredVideo object exists for this clip, and now we know that
                # its file_url is pointing to another cdn (we don't have its file in our server to be downloaded)
                # -> we need to dl the clip and upload, replacing the link of the StoredVideo with our dl
                self.logger.info("YTDLP is manually downloading this clip to be uplaoded to the server")
                await respond_to.reply("YTDLP is manually downloading this clip to be uplaoded to the server")
                response = await self.bot.tools.dl.download_clip(
                    clip=clip,
                    guild_ctx=guild,
                    always_download=True,
                    overwrite_on_server=True,
                    can_send_files=False
                )
                await respond_to.reply(f"Success for {clip_link}")
            else:
                self.logger.info(f"Video file `{the_file}` already exists on the server! Cancelling")
                await respond_to.reply("Video file already exists on the server!")
                return
        else:
            # proceed normally
            if video_doesnt_exist:
                response: DownloadResponse = await self.bot.tools.dl.download_clip(
                    clip=clip,
                    guild_ctx=guild,
                    can_send_files=will_send_files  # todo see if we wanna do this in autoembeds
                )
            else:
                self.logger.info(f" {clip.clyppy_url} - Video already exists!")
                response = DownloadResponse(
                    remote_url=None,
                    local_file_path=None,
                    duration=None,
                    width=None,
                    height=None,
                    filesize=None,
                    video_name=None,
                    can_be_uploaded=None
                )

        # send embed
        try:
            comp = []
            # refer to: ["all", "view", "dl", "none"]
            btn_idx = self.bot.guild_settings.get_embed_buttons(guild.id)
            if btn_idx <= 1:
                comp.append(Button(
                    style=ButtonStyle.LINK,
                    label=f"View On {self.platform_tools.platform_name}",
                    url=clip.url
                ))
            if (btn_idx == 0 or btn_idx == 2) and self.platform_tools.platform_name.lower() not in INVALID_DL_PLATFORMS:
                comp.append(Button(
                    style=ButtonStyle.LINK,
                    label="Download",
                    url=f"https://clyppy.io/clip-downloader?clip={clip.url}"
                ))

            if guild.is_dm:
                chn = "dm"
                chnid = 0
            else:
                chn = respond_to.channel.name
                chnid = respond_to.channel.id

            if clip.service == 'medal':
                expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=10)
                expires_at = expires_at.timestamp()
            elif clip.service == 'twitch':
                expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=10)
                expires_at = expires_at.timestamp()
            elif clip.service == 'instagram':   # idk if these actually expire
                expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=24)
                expires_at = expires_at.timestamp()
            else:
                expires_at = None
            if clip.title is not None:
                t = clip.title[:100]
            elif response.video_name is not None:
                t = response.video_name[:100]
            else:
                t = None

            uploading_to_discord = response.can_be_uploaded and has_file_perms
            if response.remote_url is None and not uploading_to_discord and video_doesnt_exist:
                self.logger.info("The remote url was None for a new video create but we're not uploading to Discord!")
                raise UnknownError

            interaction_data = {
                'edit': False,  # create new BotInteraction obj
                'create_new_video': video_doesnt_exist,
                'server_name': guild.name,
                'channel_name': chn,
                'title': t,
                'user_name': respond_to.author.username,
                'server_id': str(guild.id),
                'channel_id': str(chnid),
                'user_id': str(respond_to.author.id),
                'embedded_url': clip_link,
                'remote_file_url': response.remote_url,
                'remote_video_height': response.height,
                'remote_video_width': response.width,
                'url_platform': self.platform_tools.platform_name,
                'response_time_seconds': 0,
                'total_servers_now': len(self.bot.guilds),
                'generated_id': clip.clyppy_id,
                'original_id': clip.id,
                'video_file_size': response.filesize,
                'uploaded_to_discord': uploading_to_discord,
                'video_file_dur': response.duration,
                'expires_at_timestamp': expires_at,
                'error': error_code
            }

            try:
                try:
                    result = await publish_interaction(interaction_data, apikey=self.api_key, logger=self.logger)
                except Exception as e:
                    self.logger.info(f"Failed to post interaction to API: {e}\ninteraction_data: {interaction_data}")
                    raise

                self.logger.info(f"got back from server {result}")
                if result['success']:
                    # sometimes the server will generate a new and improved clyppy id
                    # to bypass invalid discord caches of old clyppy urls
                    if result['video_page_id']:
                        new_id = result["video_page_id"]
                        if new_id != clip.clyppy_id:
                            self.logger.info(f"Overwriting clyppy url {clip.clyppy_url} with https://clyppy.io/{new_id}")
                            clip.clyppy_id = new_id  # clyppy_url is a property() that pulls from clyppy_id
                else:
                    self.logger.info(f"Failed to publish interaction, got back from server {result}")
                    return

                if not uploading_to_discord:  # discord uploads wont have an info button
                    info_button = Button(
                        style=ButtonStyle.SECONDARY,
                        label="ⓘ Info",
                        custom_id=f"ibtn-{clip.clyppy_id}"
                    )
                    comp = [info_button] + comp
                    comp = ActionRow(*comp)

                # send message
                if isinstance(respond_to, SlashContext):
                    if uploading_to_discord:
                        await respond_to.send(file=response.local_file_path, components=comp)
                    else:
                        await respond_to.send(clip.clyppy_url, components=comp)
                else:
                    if uploading_to_discord:
                        await respond_to.reply(file=response.local_file_path, components=comp)
                    else:
                        await respond_to.reply(clip.clyppy_url, components=comp)

                if isinstance(respond_to, Message):
                    # don't publish on /embeds, we could but we need a way to pull timestamp from SlashContext
                    respond_to_utc = self._clip_id_msg_timestamps[respond_to.id]
                    my_response_time = round((datetime.now().timestamp() - respond_to_utc), 2)
                    self.logger.info(f"Successfully embedded clip {clip.id} in {guild.name} - #{chn} in {my_response_time} seconds")
                    if result['success']:
                        if my_response_time > 0:
                            await publish_interaction(my_response_time, apikey=self.api_key, edit_id=result['id'], edit_type='response_time')
                        else:
                            self.logger.info(f"Skipping edit response time for {clip.id} ({guild.name} - #{chn})...")
                    else:
                        self.logger.info(f"Failed to publish BotInteraction to server for {clip.id} ({guild.name} - #{chn})")
            except Exception as e:
                # Handle error
                self.logger.info(f"Could not send interaction: {e}")
                raise

        except errors.HTTPException as e:
            self.logger.info(f"Unknown HTTPException in _process_this_clip_link: {traceback.format_exc()}")
            emb = Embed(title="**Oops...**",
                        description=f"I messed up while trying to fetch this clip:\n{clip_link} "
                                    f"\n\nPlease try linking it again.\n"
                                    "If the issue keeps on happening, you should report this error to us!")
            emb.description += create_nexus_str()
            await self.bot.tools.send_error_message(
                ctx=respond_to,
                msg_embed=emb,
                dm_content=f"Failed to fetch clip {clip_link}",
                guild=guild,
                bot=self.bot,
                delete_after_on_reply=60
            )
            raise
        except Exception:
            self.logger.info(f"Unknown Exception in _process_this_clip_link: {traceback.format_exc()}")
            emb = Embed(title="**Oops...**",
                        description=f"I messed up while trying to fetch this clip:\n{clip_link} "
                                    f"\n\nPlease try linking it again.\n"
                                    "If the issue keeps on happening, you should report this error to us!")
            emb.description += create_nexus_str()
            await self.bot.tools.send_error_message(
                ctx=respond_to,
                msg_embed=emb,
                dm_content=f"Failed to fetch clip {clip_link}",
                guild=guild,
                bot=self.bot,
                delete_after_on_reply=60
            )
            raise

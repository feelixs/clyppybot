import logging
import traceback
from interactions import SlashContext
from dataclasses import dataclass
from bot.tools.dl import DownloadManager
import os


POSSIBLE_TOO_LARGE = ["trim", "info", "dm"]
POSSIBLE_ON_ERRORS = ["dm", "info"]
POSSIBLE_EMBED_BUTTONS = ["all", "view", "dl", "none"]


SUPPORT_SERVER_URL = "https://discord.gg/Xts5YMUbeS"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1111723928604381314&permissions=182272&scope=bot%20applications.commands"
TOPGG_VOTE_LINK = "https://top.gg/bot/1111723928604381314/vote"
INFINITY_VOTE_LINK = "https://infinitybots.gg/bot/1111723928604381314/vote"
DLIST_VOTE_LINK = "https://discordbotlist.com/bots/clyppy/upvote"
BOTLISTME_VOTE_LINK = "https://botlist.me/bots/1111723928604381314/vote"
DL_SERVER_ID = os.getenv("DL_SERVER_ID")

@dataclass
class GuildType:
    id: int
    name: str
    is_dm: bool


def create_nexus_str():
    return f"\n\n**[Invite Clyppy]({INVITE_LINK}) | [Report an Issue]({SUPPORT_SERVER_URL}) | [Vote for me!]({TOPGG_VOTE_LINK})**"


class Tools:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.dl = DownloadManager(self)

    async def send_error_message(self, msg_embed, dm_content, guild, ctx, bot, delete_after_on_reply=None):
        if isinstance(ctx, SlashContext):
            return
        err = ""
        if guild.id == ctx.author.id:
            pass  # don't use 'dm' setting if we're already in a dm, just reply
        elif bot.guild_settings.is_dm_on_error(guild.id):
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

from interactions import Client
from bot.platforms.dailymotion import DailymotionMisc
from bot.platforms.drive import GoogleDriveMisc
from bot.platforms.insta import InstagramMisc
from bot.platforms.tiktok import TikTokMisc
from bot.platforms.twitch import TwitchMisc
from bot.platforms.reddit import RedditMisc
from bot.platforms.bsky import BlueSkyMisc
from bot.platforms.vimeo import VimeoMisc
from bot.platforms.r34 import R34Misc
from bot.platforms.medal import MedalMisc
from bot.platforms.youtube import YtMisc
from bot.platforms.bili import BiliMisc
from bot.platforms.kick import KickMisc
from bot.platforms.phub import PhubMisc
from bot.platforms.youp import YoupoMisc
from bot.platforms.xvid import XvidMisc
from bot.platforms.base import BASIC_MISC
from bot.platforms.discord_attach import DiscordMisc
from bot.platforms.x import Xmisc
from bot.tools.misc import Tools
from bot.classes import BaseAutoEmbed
import logging


class BaseEmbedder(BaseAutoEmbed):
    def __init__(self, bot):
        self.bot = bot
        self.is_base = True
        self.logger = logging.getLogger(self.__class__.__name__)
        self.platform = BASIC_MISC(bot)
        super().__init__(
            platform=self.platform,
            always_embed=False
        )


def init_misc(bot: Client) -> Client:
    bot.base_embedder = BaseEmbedder(bot=bot)
    bot.twitch = TwitchMisc(bot=bot)
    bot.kick = KickMisc(bot=bot)
    bot.insta = InstagramMisc(bot=bot)
    bot.medal = MedalMisc(bot=bot)
    bot.dailymotion = DailymotionMisc(bot=bot)
    bot.reddit = RedditMisc(bot=bot)
    bot.yt = YtMisc(bot=bot)
    bot.youp = YoupoMisc(bot=bot)
    bot.x = Xmisc(bot=bot)
    bot.xvid = XvidMisc(bot=bot)
    bot.r34 = R34Misc(bot=bot)
    bot.bsky = BlueSkyMisc(bot=bot)
    bot.bili = BiliMisc(bot=bot)
    bot.phub = PhubMisc(bot=bot)
    bot.tiktok = TikTokMisc(bot=bot)
    bot.vimeo = VimeoMisc(bot=bot)
    bot.drive = GoogleDriveMisc(bot=bot)
    bot.dsc = DiscordMisc(bot=bot)
    bot.tools = Tools()

    bot.currently_embedding = []  # used in embedder.py (AutoEmbedder) -> for quickembeds (and i guess also triggers for command embeds)
    bot.currently_downloading = []  # used in command embeds across all platforms
    bot.currently_embedding_users = []  # used for command embeds

    bot.platform_list = [
        bot.twitch,
        bot.kick,
        bot.insta,
        bot.medal,
        bot.reddit,
        bot.yt,
        bot.x,
        bot.bsky,
        bot.tiktok,
        bot.r34,
        bot.xvid,
        bot.phub,
        bot.youp,
        bot.vimeo,
        bot.bili,
        bot.dailymotion,
        bot.drive,
        bot.dsc
    ]

    quickembed_platforms = ['kick', 'twitch']
    bot.platform_embedders = [
        BaseAutoEmbed(
            platform=platform,
            always_embed=[platform.platform_name in quickembed_platforms]
        )
        for platform in bot.platform_list
    ]
    bot.platform_embedders.append(bot.base_embedder)

    return bot

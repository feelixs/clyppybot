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
from bot.platforms.nuuls import NuulsMisc
from bot.platforms.discord_attach import DiscordMisc
from bot.platforms.x import Xmisc
from bot.tools.misc import Tools
from bot.classes import BaseAutoEmbed
import logging


class BaseAutoEmbedForConsistency(BaseAutoEmbed):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        self.platform = None
        super().__init__(self)


def init_misc(bot):
    bot.base = BaseAutoEmbedForConsistency(bot=bot)
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
    bot.nuuls = NuulsMisc(bot=bot)
    bot.vimeo = VimeoMisc(bot=bot)
    bot.drive = GoogleDriveMisc(bot=bot)
    bot.dsc = DiscordMisc(bot=bot)
    bot.tools = Tools()

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
        bot.nuuls,
        bot.dsc
    ]

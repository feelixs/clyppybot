from interactions import Button, ButtonStyle
import os


def create_nexus_comps():
    return [
        Button(style=ButtonStyle.LINK, url=INVITE_LINK, label='Invite Clyppy'),
        Button(style=ButtonStyle.LINK, url=SUPPORT_SERVER_URL, label='Support Server'),
        Button(style=ButtonStyle.LINK, url=CLYPPY_VOTE_URL, label='Vote for me!'),
    ]


YT_DLP_MAX_FILESIZE = 1610612736 * 4  # 6GB in bytes (1.5 * 1024 * 1024 * 1024 * 4) should handle most 3 hour videos

YT_DLP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"

EMBED_TXT_COMMAND = ".embed"

LOGGER_WEBHOOK = os.getenv('LOG_WEBHOOK')
APPUSE_LOG_WEBHOOK = os.getenv('APPUSE_WEBHOOK')

VERSION = "2.1.1"
CLYPPYIO_USER_AGENT = f"ClyppyBot/{VERSION}"

EMBED_TOKEN_COST = 1
EMBED_W_TOKEN_MAX_LEN = 30 * 60  # 30 minutes
EMBED_TOTAL_MAX_LENGTH = 4 * 60 * 60  # 4 hours
MAX_VIDEO_LEN_SEC = 60 * 5

MAX_FILE_SIZE_FOR_DISCORD = 8 * 1024 * 1024
DL_SERVER_ID = os.getenv("DL_SERVER_ID")
POSSIBLE_TOO_LARGE = ["trim", "info", "dm"]
POSSIBLE_ON_ERRORS = ["dm", "info"]
POSSIBLE_EMBED_BUTTONS = ["all", "view", "dl", "none"]

CLYPPYBOT_ID = 1111723928604381314

DOWNLOAD_THIS_WEBHOOK_ID = 1331035236041097326
CLYPPY_VIDEO_REFRESHER_ID = 1361758046950396417
CLYPPY_CMD_WEBHOOK_ID = 1352361462005370983
CLYPPY_CMD_WEBHOOK_CHANNEL = 1352361327770992690

CLYPPY_SUPPORT_SERVER_ID = 1117149574730104872
CLYPPY_VOTE_ROLE = 1337067081941647472
VOTE_WEBHOOK_USERID = 1337076281040179240

SUPPORT_SERVER_URL = "https://discord.gg/Xts5YMUbeS"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1111723928604381314"
TOPGG_VOTE_LINK = "https://top.gg/bot/1111723928604381314/vote"
INFINITY_VOTE_LINK = "https://infinitybots.gg/bot/1111723928604381314/vote"
DLIST_VOTE_LINK = "https://discordbotlist.com/bots/clyppy/upvote"
BOTLISTME_VOTE_LINK = "https://botlist.me/bots/1111723928604381314/vote"
CLYPPY_VOTE_URL = "https://clyppy.io/vote/"


NSFW_DOMAIN_TRIGGERS = ['porn', 'sex']
EXTRA_YT_DLP_SUPPORTED_NSFW_DOMAINS = [
    'xhamster',
    'xstream',
    'xxxymovies',
    'youjizz',
    '4tube',
    'tube8',
    'cam4',
    'camsoda',
    'fux',
    'xvideos',
    'redtube',
    'motherless',
    'moviefap',
    'murrtube',
    'peekvids',
    'redgifs',
    'slutload',
    'spankbang',
    'gelbooru',
    'stripchat',
    'noodlemagazine',
    'tnaflix'
]

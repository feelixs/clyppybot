import os


YT_DLP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"

EMBED_TXT_COMMAND = "!embed"

LOGGER_WEBHOOK = os.getenv('LOG_WEBHOOK')
APPUSE_LOG_WEBHOOK = os.getenv('APPUSE_WEBHOOK')

VERSION = "1.5.8b"
CLYPPYIO_USER_AGENT = f"ClyppyBot/{VERSION}"



MAX_VIDEO_LEN_SEC = 60 * 5
MAX_FILE_SIZE_FOR_DISCORD = 8 * 1024 * 1024
DL_SERVER_ID = os.getenv("DL_SERVER_ID")
POSSIBLE_TOO_LARGE = ["trim", "info", "dm"]
POSSIBLE_ON_ERRORS = ["dm", "info"]
POSSIBLE_EMBED_BUTTONS = ["all", "view", "dl", "none"]


SUPPORT_SERVER_URL = "https://discord.gg/Xts5YMUbeS"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1111723928604381314&permissions=182272&scope=bot%20applications.commands"
TOPGG_VOTE_LINK = "https://top.gg/bot/1111723928604381314/vote"
INFINITY_VOTE_LINK = "https://infinitybots.gg/bot/1111723928604381314/vote"
DLIST_VOTE_LINK = "https://discordbotlist.com/bots/clyppy/upvote"
BOTLISTME_VOTE_LINK = "https://botlist.me/bots/1111723928604381314/vote"


EMBED_TOKEN_COST = 1
EMBED_W_TOKEN_MAX_LEN = 30 * 60  # 30 minutes

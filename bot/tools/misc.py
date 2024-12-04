from interactions import Message

SUPPORT_SERVER_URL = "https://discord.gg/Xts5YMUbeS"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1111723928604381314&permissions=182272&scope=bot%20applications.commands"
TOPGG_VOTE_LINK = "https://top.gg/bot/1111723928604381314/vote"


def create_nexus_str():
    return f"\n\n**[Invite CLYPPY]({INVITE_LINK}) | [Suggest a Feature]({SUPPORT_SERVER_URL}) | [Vote for me!]({TOPGG_VOTE_LINK})**"


async def reply_if_loud(bot, parent: Message, content: str = None, file=None, embed=None, delete_after=None):
    silent = bot.guild_settings.get_silent(parent.guild.id) or True
    if not silent:
        await parent.reply(content, file=file, embed=embed, delete_after=delete_after)
    else:
        # if silent, we need to dm them, and we cant use the other params there
        await parent.author.user.get_dm().send(content)

from interactions import Message

SUPPORT_SERVER_URL = "https://discord.gg/Xts5YMUbeS"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1111723928604381314&permissions=182272&scope=bot%20applications.commands"
TOPGG_VOTE_LINK = "https://top.gg/bot/1111723928604381314/vote"


def create_nexus_str():
    return f"\n\n**[Invite CLYPPY]({INVITE_LINK}) | [Suggest a Feature]({SUPPORT_SERVER_URL}) | [Vote for me!]({TOPGG_VOTE_LINK})**"


async def reply_or_dm(bot, parent: Message, content: str = None, file=None, embed=None, delete_after=None):
    silent = bot.guild_settings.get_silent(parent.guild.id) or True
    if silent:
        # if silent, dm them
        await parent.author.user.get_dm().send(content, embed=embed, file=file)
    else:
        await parent.reply(content, file=file, embed=embed, delete_after=delete_after)

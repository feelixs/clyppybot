from interactions import Extension, listen
from interactions.api.events import MessageCreate
import logging
import re


CLYPPY_SUPPORT_SERVER_ID = 1117149574730104872
CLYPPY_VOTE_ROLE = 1337067081941647472
VOTE_WEBHOOK_USERID = 1337076281040179240


class Watch(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    async def give_votes_roles(self, userid, total_votes: int):
        # when the 'server' webhook posts a new vote happened in CLYPPY CLUB server
        # this extension will give the voter the corresponding role in that server

        guild = self.bot.get_guild(CLYPPY_SUPPORT_SERVER_ID)
        try:
            member = await guild.fetch_member(userid)
            if member is None:
                self.logger.info(f"Could not find member with ID {userid}")
                return
            self.logger.info(f"Giving vote roles to {member.username}")
            voter_role = await guild.fetch_role(CLYPPY_VOTE_ROLE)
            if voter_role is None:
                self.logger.info(f"Could not find voter role with ID {CLYPPY_VOTE_ROLE}")
                return
        except Exception as e:
            self.logger.info(f"Error getting member or role: {e}")
            return

        the_role, old_roles = None, []
        for r in guild.roles:
            if match := re.match(r'(\d+) Votes?', r.name):
                role_votes = int(match.group(1))
                if role_votes == total_votes:
                    self.logger.info(f"Setting role {r.name} because it has {total_votes} votes")
                    the_role = r
                elif role_votes < total_votes:
                    self.logger.info(f"Removing role {r.name} because it has less votes than {total_votes}")
                    old_roles.append(r)

        if the_role is None:
            self.logger.info(f"Creating role `{total_votes} Votes` because it doesn't exist")
            the_role = await guild.create_role(name=f"{total_votes} Votes")

        await member.remove_roles(old_roles)
        await member.add_roles([voter_role, the_role])

    @listen(MessageCreate)
    async def on_message_create(self, event):
        if event.message.guild is None:
            return  # in dms it won't work

        if "clyppy" in event.message.content or '1111723928604381314' in event.message.content:
            self.logger.info(f"{event.message.guild.name}: #{event.message.channel.name} "
                             f"@{event.message.author.username} - \"{event.message.content}\"")

            if event.message.author.id == VOTE_WEBHOOK_USERID:
                pattern = r"<@(\d+)> just gave \((\d+)\) vote\(s\) for <@\d+> on \[[^\]]+\]\([^)]+\) and earned \d+ VIP tokens, they now have (\d+) votes in total"
                match = re.match(pattern, event.message.content)
                if match:
                    userid = int(match.group(1))
                    votes_given = match.group(2)
                    vote_total = int(match.group(3))
                    await self.give_votes_roles(userid, vote_total)
                else:
                    self.logger.info(f"Couldn't match pattern")

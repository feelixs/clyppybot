from bot.env import CLYPPY_SUPPORT_SERVER_ID, CLYPPY_CMD_WEBHOOK_ID, CLYPPY_CMD_WEBHOOK_CHANNEL, CLYPPY_VOTE_ROLE, VOTE_WEBHOOK_USERID, CLYPPYBOT_ID
from interactions import Extension, listen
from interactions.api.events import MessageCreate
import logging
import asyncio
from bot.io import add_reqqed_by
import re


class Watch(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    async def give_votes_roles(self, userid: int, total_votes: int):
        # when the 'server' webhook posts a new vote happened in CLYPPY CLUB server
        # this extension will give the voter the corresponding role in that server

        guild = self.bot.get_guild(CLYPPY_SUPPORT_SERVER_ID)
        try:
            member = await guild.fetch_member(userid)
            if member is None:
                self.logger.info(f"Could not find member with ID {userid} ({type(userid)})")
                return
            self.logger.info(f"Giving vote roles to {member.username}")
            voter_role = await guild.fetch_role(CLYPPY_VOTE_ROLE)
            if voter_role is None:
                self.logger.info(f"Could not find voter role with ID {CLYPPY_VOTE_ROLE} ({type(CLYPPY_VOTE_ROLE)})")
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

        if event.message.author.id in [CLYPPYBOT_ID, 1305624117818560664]:
            # clyppy or test clyppy (cassandra) sent msg
            return

        if "clyppy" in event.message.content or str(CLYPPYBOT_ID) in event.message.content:
            self.logger.info(f"{event.message.guild.name}: #{event.message.channel.name} "
                             f"@{event.message.author.username} - \"{event.message.content}\"")

            if event.message.author.id == VOTE_WEBHOOK_USERID:  # vote webhook sent a new vote registered
                pattern = r"<@(\d+)> just gave \((\d+)\) vote\(s\) for <@\d+> on \[[^\]]+\]\([^)]+\) and earned \d+ VIP tokens, they now have (\d+) votes in total"
                match = re.match(pattern, event.message.content)
                if match:
                    userid = int(match.group(1))
                    votes_given = match.group(2)
                    vote_total = int(match.group(3))
                    await self.give_votes_roles(userid, vote_total)
                else:
                    self.logger.info(f"Couldn't match pattern")

            elif event.message.author.id == CLYPPY_CMD_WEBHOOK_ID:  # cmd webhook sent a command to clyppy (delete a msg, etc)
                # should only work in this channel (unneeded validation)
                if event.message.channel.id != CLYPPY_CMD_WEBHOOK_CHANNEL:
                    return

                pattern = fr"<@{CLYPPYBOT_ID}>: <@(\d+)> \((\d+)\) said to delete these: \[(.*?)\]"
                match = re.search(pattern, event.message.content)
                
                delete_tasks = []
                if match:
                    # Get the list of IDs from the third group
                    id_list_str = match.group(3)
                    # Extract individual IDs (handling both quoted and unquoted formats)
                    message_ids = re.findall(r"'([\d-]+)'|\"([\d-]+)\"|(\d+-\d+)", id_list_str)
                    
                    for match_groups in message_ids:
                        # Each match is a tuple with 3 possible groups - find the non-empty one
                        fullstr = next((group for group in match_groups if group), None)
                        if fullstr:
                            parts = fullstr.split('-')
                            if len(parts) == 2:
                                chnid, msgid = parts[0], parts[1]
                                try:
                                    if chnid.startswith('d'):
                                        # Handle DM channel case
                                        userid = chnid[1:]  # Remove the 'd' prefix to get the user ID
                                        user = await self.bot.fetch_user(userid)
                                        self.logger.info(f"Fetching dm with user {user.username}")
                                        dm_channel = await user.fetch_dm(force=True)
                                        msg = await dm_channel.fetch_message(msgid)
                                    else:
                                        chn = await self.bot.fetch_channel(chnid)
                                        msg = await chn.fetch_message(msgid)
                                    delete_tasks.append(asyncio.create_task(msg.delete()))
                                except Exception as e:
                                    self.logger.error(f"Error fetching message {fullstr}: {e}")
                else:
                    self.logger.info(f"No match found for delete command in: {event.message.content}")

                await asyncio.gather(*delete_tasks)

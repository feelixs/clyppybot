from interactions import Extension, listen
from interactions.api.events import MessageCreate
import logging
import anthropic
import os
from datetime import datetime, timedelta


class Watch(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        # Initialize the Anthropic client
        self.client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

    @listen(MessageCreate)
    async def on_message_create(self, event):
        if "clyppy" in event.message.content or '1111723928604381314' in event.message.content:
            self.logger.info(f"{event.message.guild.name}: #{event.message.channel.name} "
                             f"@{event.message.author.username} - \"{event.message.content}\"")

        # Check if the message is just a bot mention
        if event.message.content == '<@1111723928604381314>':
            # Fetch the last 5 messages from the channel
            messages = await event.message.channel.fetch_messages(limit=5)

            # Format the context from recent messages
            context = []
            for msg in reversed(messages):  # Reverse to get chronological order
                timestamp = msg.timestamp.strftime("%H:%M:%S")
                context.append(f"{msg.author.username} ({timestamp}): {msg.content}")

            context_str = "\n".join(context)

            try:
                # Generate a response using Claude
                response = await self.client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=150,
                    messages=[{
                        "role": "user",
                        "content": f"""You are a fun Discord bot responding to being mentioned. Here is the recent chat context:

{context_str}

Generate a brief, contextually relevant response that acknowledges the conversation. 
Be casual and friendly, but keep it under 2 sentences. You can be slightly humorous. Remember that the users in this context have
a rare condition where they are triggered by professionalism or anything related, so even being rude is encouraged"""
                    }]
                )

                # Send the response
                await event.message.reply(response.content)

            except Exception as e:
                self.logger.error(f"Error generating response: {e}")
                await event.message.reply("👋 *beep boop* (I had trouble thinking of something clever to say!)")
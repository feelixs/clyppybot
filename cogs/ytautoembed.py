from interactions import Extension, listen
from interactions.api.events import MessageCreate
from bot.tools import AutoEmbedder
import logging


class YtAutoEmbed(Extension):
    def __init__(self, bot):
        self.embedder = AutoEmbedder(bot, bot.yt, logging.getLogger(__name__))

    # don't auto embed yt links, should only work via /embed command
    @listen(MessageCreate)
    async def on_message_create(self, event):
        if self.bot.yt.is_dl_server(event.message.guild):
            await self.embedder.on_message_create(event)

    @listen()
    async def on_raw_gateway_event(self, event):
        # Try to access the event type differently
        try:
            # Check if it's an invite create event by looking at event properties
            # Sometimes the event type is in event.event_type or event.t
            event_type = getattr(event, "event_type", None) or getattr(event, "t", None)

            if event_type == "INVITE_CREATE":
                self.embedder.logger.info(f"Raw invite data received: {event.data}")

                # Print the entire event object to understand its structure
                self.embedder.logger.info(f"Full event structure: {dir(event)}")

                # If data is available, check for target_application
                if hasattr(event, "data") and "target_application" in event.data:
                    self.embedder.logger.info(f"target_application data: {event.data['target_application']}")
        except Exception as e:
            self.embedder.logger.info(f"Error inspecting event: {e}")
            self.embedder.logger.info(f"Event attributes: {dir(event)}")
from bot.classes import BaseAutoEmbed


class DriveAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.drive)

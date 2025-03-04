from bot.classes import BaseAutoEmbed


def setup(bot):
    bot.add_extension(DriveAutoEmbed(bot))


class DriveAutoEmbed(BaseAutoEmbed):
    def __init__(self, bot):
        super().__init__(bot, bot.drive)

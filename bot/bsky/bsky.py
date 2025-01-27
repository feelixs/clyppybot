import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong


class BlueSkyMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "BlueSky"

    def parse_clip_url(self, url: str) -> str:
        """
        Extracts the post ID from various BlueSky URL formats.
        Returns None if the URL is not a valid BlueSky URL.
        """
        pattern = r'(?:https?://)?(?:www\.)?bsky\.app/profile/([^/]+)/post/([^/]+)'
        match = re.match(pattern, url)
        if match:
            return match.group(2)
        return None

    async def get_clip(self, url: str) -> 'BlueSkyClip':
        slug = self.parse_clip_url(url)
        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        # Extract user handle from URL
        user_match = re.search(r'bsky\.app/profile/([^/]+)/post/', url)
        user = user_match.group(1) if user_match else None

        return BlueSkyClip(slug, user)


class BlueSkyClip(BaseClip):
    def __init__(self, slug, user):
        self._service = "bluesky"
        self._url = f"https://bsky.app/profile/{user}/post/{slug}"
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url
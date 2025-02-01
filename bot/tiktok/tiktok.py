import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong, NoDuration


class TikTokMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "TikTok"

    def parse_clip_url(self, url: str) -> str:
        """
        Extracts the TikTok video ID from various URL formats.
        Returns None if the URL is not a valid TikTok video URL.
        """
        # Mathes URLs like:
        # - https://www.tiktok.com/@username/video/123456789
        # - https://m.tiktok.com/video/123456789
        # - https://vm.tiktok.com/video/123456789
        pattern = r'(?:https?://)?(?:www\.|vm\.|m\.)?tiktok\.com/(?:@[^/]+/)?video/(\d+)'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    async def get_clip(self, url: str) -> 'TikTokClip':
        video_id = self.parse_clip_url(url)
        if not video_id:
            self.logger.info(f"Invalid TikTok URL: {url}")
            raise NoDuration

        # Verify video length (assuming all TikTok videos are short-form)
        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        # Extract username if available
        user_match = re.search(r'tiktok\.com/@([^/]+)/', url)
        user = user_match.group(1) if user_match else None

        return TikTokClip(video_id, user)


class TikTokClip(BaseClip):
    def __init__(self, video_id, user):
        self._service = "tiktok"
        self._user = user
        self._video_id = video_id
        super().__init__(video_id)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        if self._user:
            return f"https://www.tiktok.com/@{self._user}/video/{self._video_id}"
        return f"https://www.tiktok.com/video/{self._video_id}"

    # todo, add this to main and run it in tester to see if it works

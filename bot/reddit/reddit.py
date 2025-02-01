import logging
import yt_dlp
import re
import asyncio
import aiohttp
import os
from typing import Optional, Tuple
from bot.kick import KickMisc
from bot.classes import BaseClip, BaseMisc, VideoTooLong, NoDuration


class RedditMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Reddit"
        self.VALID_EXT_VIDEO_DOMAINS = [
            'twitch.tv',
            'www.twitch.tv',
            'kick.com',
            'www.kick.com',
            'medal.tv',
            'www.medal.tv',
        ]

    def parse_clip_url(self, url: str) -> (str, str):
        """
        Extracts the post ID from a Reddit URL if present.
        Works with all supported URL formats.

        Args:
            url (str): Reddit URL

        Returns:
            str | None: Post ID if found, None otherwise
        """
        # Try to extract post ID from various URL formats
        patterns = [
            r'(?:https?://)?(?:www\.)?reddit\.com/r/[^/]+/comments/([a-zA-Z0-9]+)',  # Standard format
            r'(?:https?://)?(?:www\.)?redd\.it/([a-zA-Z0-9]+)',  # Short links
            r'(?:https?://)?(?:www\.)?reddit\.com/gallery/([a-zA-Z0-9]+)',  # Gallery links
            r'(?:https?://)?(?:www\.)?reddit\.com/user/[^/]+/comments/([a-zA-Z0-9]+)',  # User posts
            r'(?:https?://)?(?:www\.)?reddit\.com/r/[^/]+/duplicates/([a-zA-Z0-9]+)',  # Crossposts
            r'(?:https?://)?(?:www\.)?reddit\.com/r/[^/]+/s/([a-zA-Z0-9]+)'  # Share links
        ]

        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def is_video(self, url: str, max_redirects: int = 3) -> tuple[bool, Optional[str]]:
        """
        Check if a Reddit post contains a video or links to a video platform.

        Args:
            url (str): The Reddit post URL to check
            max_redirects (int): Maximum number of redirects to follow for shreddit-redirect

        Returns:
            tuple[bool, Optional[str]]: (True if video found, domain name if found else None)
            For v.redd.it videos, returns (True, None)
            For external platforms, returns (True, full_platform_url)
        """
        if max_redirects <= 0:
            logging.warning(f"Max redirects reached for URL: {url}")
            return False, None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        logging.warning(f"Got status {response.status} for URL: {url}")
                        return False, None
                    txt = await response.text()
                    # Handle shreddit redirects
                    if "redd.it" in url and "shreddit-redirect" in txt:
                        try:
                            redirect_url = "https://reddit.com/" + \
                                           txt.split("shreddit-redirect href=\"")[-1].split("\"")[0]
                            return await self.is_video(redirect_url, max_redirects - 1)
                        except IndexError:
                            logging.error(f"Failed to parse shreddit redirect in: {url}")
                            return False, None
                    # First check for v.redd.it videos
                    if 'v.redd.it' in txt:
                        return True, None
                    # Check for external platform links
                    for domain in self.VALID_EXT_VIDEO_DOMAINS:
                        if domain in txt:
                            try:
                                matches = re.findall(f'https?://(?:www\.)?{domain}[^\s"\'<>]+', txt)
                                if matches:
                                    return True, matches[0].split("&")[0]
                            except Exception as e:
                                self.logger.error(f"Error extracting external URL: {str(e)}")
                    return False, None

        except aiohttp.ClientError as e:
            logging.error(f"Error fetching URL {url}: {str(e)}")
            return False, None
        except Exception as e:
            logging.error(f"Unexpected error checking video for {url}: {str(e)}")
            return False, None

    def is_clip_link(self, url: str) -> bool:
        """
                Checks if a URL is a valid Reddit link format.
                Handles various Reddit URL patterns including short links, galleries,
                user posts, crossposts, and mobile versions.

                Args:
                    url (str): URL to check
                Returns:
                    bool: True if URL matches any known Reddit format
                """
        patterns = [
            # Standard post URLs (www, old, and bare domain)
            r'https?://(?:www\.|old\.)?reddit\.com/r/[a-zA-Z0-9_-]+/comments/[a-zA-Z0-9]+(?:/[^/]+/?)?(?:\?[^/]+)?',
            # Short links
            r'https?://(?:www\.)?redd\.it/[a-zA-Z0-9]+',
            # Gallery links
            r'https?://(?:www\.)?reddit\.com/gallery/[a-zA-Z0-9]+',
            # User profile posts
            r'https?://(?:www\.|old\.)?reddit\.com/user/[a-zA-Z0-9_-]+/comments/[a-zA-Z0-9]+(?:/[^/]+/?)?(?:\?[^/]*)?',
            # Crosspost/duplicate links
            r'https?://(?:www\.)?reddit\.com/r/[a-zA-Z0-9_-]+/duplicates/[a-zA-Z0-9]+(?:/[^/]+/?)?',
            # Mobile versions (i.reddit and m.reddit)
            r'https?://[im]\.reddit\.com/r/[a-zA-Z0-9_-]+/comments/[a-zA-Z0-9]+(?:/[^/]+/?)?',
            # Share links
            r'https?://(?:www\.)?reddit\.com/r/[a-zA-Z0-9_-]+/s/[a-zA-Z0-9]+'
        ]
        # Combine all patterns with OR operator
        combined_pattern = '|'.join(f'({pattern})' for pattern in patterns)
        return bool(re.match(combined_pattern, url))

    async def _get_actual_slug(self, share_url):
        async with aiohttp.ClientSession() as session:
            async with session.get(share_url, timeout=10) as response:
                if response.status != 200:
                    logging.warning(f"Got status {response.status} for URL: {share_url}")
                    raise IndexError
                txt = await response.text()
                link = txt.split("shreddit-canonical-url-updater value=\"")[-1].split("\"")[0]
                return self.parse_clip_url(link)

    async def get_clip(self, url: str) -> 'RedditClip':
        slug = self.parse_clip_url(url)
        is_vid, ext_info = await self.is_video(url)
        if not is_vid:
            self.logger.info(f"{url} is_video=False")
            raise NoDuration
        self.logger.info(f"{url} is_video=True")

        if re.match(r'https?://(?:www\.)?reddit\.com/r/[a-zA-Z0-9_-]+/s/[a-zA-Z0-9]+', url):  # retrieve the actual slug from a share link
            try:
                slug = await self._get_actual_slug(url)
                self.logger.info(f"Retrieving actual slug from shared url {url}")
            except:
                raise NoDuration

        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        return RedditClip(slug, ext_info)


class RedditClip(BaseClip):
    def __init__(self, slug, ext):
        self._service = "reddit"
        self._url = f"https://redd.it/{slug}"
        self.external_link = ext
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def _download_kick(self, filename, dlp_format='best/bv*+ba', can_send_files=False) -> Optional[Tuple[str, float]]:
        k = KickMisc()
        kclip = await k.get_clip(self.external_link)
        return await kclip.download(filename, dlp_format, can_send_files)

    async def download(self, filename: str = None, dlp_format='best/bv*+ba', can_send_files=False) -> Optional[Tuple[str, float]]:
        if self.external_link is None:
            pass
        elif 'kick' in self.external_link:  # external_platform is a domain
            self.logger.info(f"Running download for external link {self.external_link}")
            return await self._download_kick(filename, dlp_format, can_send_files)
        return await super().download(filename=filename, dlp_format=dlp_format, can_send_files=can_send_files)

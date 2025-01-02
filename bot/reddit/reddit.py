import logging
import yt_dlp
import re
import asyncio
import aiohttp
import os


class RedditMisc:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.platform_name = "Reddit"
        self.silence_invalid_url = True
        self.VALID_VIDEO_DOMAINS = [
            'twitch.tv',
            'www.twitch.tv',
            'kick.com',
            'www.kick.com',
            'medal.tv',
            'www.medal.tv',
            'v.redd.it'
        ]

    @staticmethod
    def parse_clip_url(url: str) -> (str, str):
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
            r'reddit\.com/r/[^/]+/comments/([a-zA-Z0-9]+)',  # Standard format
            r'redd\.it/([a-zA-Z0-9]+)',                      # Short links
            r'reddit\.com/gallery/([a-zA-Z0-9]+)',          # Gallery links
            r'reddit\.com/user/[^/]+/comments/([a-zA-Z0-9]+)',  # User posts
            r'reddit\.com/r/[^/]+/duplicates/([a-zA-Z0-9]+)',   # Crossposts
            r'reddit\.com/r/[^/]+/s/([a-zA-Z0-9]+)'          # Share links
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    async def is_video(self, url: str, max_redirects: int = 3) -> bool:
        """
        Check if a Reddit post contains a video or links to a video platform.

        Args:
            url (str): The Reddit post URL to check
            max_redirects (int): Maximum number of redirects to follow for shreddit-redirect

        Returns:
            bool: True if the post contains a video or links to a video platform

        Raises:
            aiohttp.ClientError: If there's an error fetching the URL
        """
        if max_redirects <= 0:
            logging.warning(f"Max redirects reached for URL: {url}")
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        logging.warning(f"Got status {response.status} for URL: {url}")
                        return False
                    txt = await response.text()

                    # Handle shreddit redirects
                    if "redd.it" in url and "shreddit-redirect" in txt:
                        try:
                            redirect_url = "https://reddit.com/" + \
                                           txt.split("shreddit-redirect href=\"")[-1].split("\"")[0]
                            return await self.is_video(redirect_url, max_redirects - 1)
                        except IndexError:
                            logging.error(f"Failed to parse shreddit redirect in: {url}")
                            return False

                    # Check for embedded video or video platform links
                    return any(
                        domain in txt
                        for domain in self.VALID_VIDEO_DOMAINS
                    )

        except aiohttp.ClientError as e:
            logging.error(f"Error fetching URL {url}: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error checking video for {url}: {str(e)}")
            return False

    @staticmethod
    def is_clip_link(url: str) -> bool:
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

    async def get_clip(self, url: str) -> 'RedditClip':
        slug = self.parse_clip_url(url)
        if not await self.is_video(url):
            self.logger.info(f"{url} is_video=False")
            return None
        self.logger.info(f"{url} is_video=True")
        return RedditClip(slug)


class RedditClip:
    def __init__(self, slug):
        self.id = slug
        self.service = "reddit"
        self.url = f"https://redd.it/{slug}"
        self.logger = logging.getLogger(__name__)

    async def download(self, filename: str):
        self.logger.info(f"Downloading with yt-dlp: {filename}")
        ydl_opts = {
            'format': 'best/bv*+ba',
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True,
        }

        # Download using yt-dlp
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Run download in a thread pool to avoid blocking
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: ydl.download([self.url])
                )

            if os.path.exists(filename):
                return filename
            self.logger.info(f"Could not find file")
            return None
        except Exception as e:
            self.logger.error(f"yt-dlp download error: {str(e)}")
            return None

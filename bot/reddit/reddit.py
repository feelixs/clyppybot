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

    @staticmethod
    def parse_clip_url(url: str) -> (str, str):
        """
        Extracts post ID and subreddit from Reddit URL
        Returns: (post_id, subreddit_name)
        """
        pattern = r'https?://(?:www\.|old\.)?reddit\.com/r/([a-zA-Z0-9_-]+)/comments/([a-zA-Z0-9]+)'
        match = re.match(pattern, url)
        if not match:
            raise ValueError("Invalid Reddit URL")
        subreddit, post_id = match.groups()
        return post_id, subreddit

    @staticmethod
    async def is_video(url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return "v.redd.it" in await response.text()

    @staticmethod
    def is_clip_link(url: str) -> bool:
        # Pattern matches Reddit post URLs like:
        # https://www.reddit.com/r/subreddit/comments/postid/title
        # https://old.reddit.com/r/subreddit/comments/postid/title
        # https://reddit.com/r/subreddit/comments/postid/title
        pattern = r'https?://(?:www\.|old\.)?reddit\.com/r/[a-zA-Z0-9_-]+/comments/[a-zA-Z0-9]+(?:/[^/]+/?)?'
        return bool(re.match(pattern, url))

    async def get_clip(self, url: str) -> 'RedditClip':
        slug, subreddit = self.parse_clip_url(url)
        if not self.is_video(url):
            return None
        return RedditClip(slug, subreddit)


class RedditClip:
    def __init__(self, slug, sub):
        self.id = slug
        self.service = "reddit"
        self.url = f"https://reddit.com/{sub}/comments/{slug}"
        self.logger = logging.getLogger(__name__)

    async def download(self, filename: str):
        self.logger.info(f"Downloading with yt-dlp: {filename}")
        ydl_opts = {
            'format': 'best',
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
from datetime import datetime
import time
import aiohttp
import asyncio
from os import path
from bot.errors import RateLimitExceededError, TooManyTriesError


MY_USAGE_RATE = 800  # default is 800 requests per minute


class TwitchAPI:
    def __init__(self, key: str, secret: str, logger, log_path: str = None, allowed_tries: int = 5):
        self.key = key
        self.logger = logger
        self.usage_remaining = MY_USAGE_RATE
        self.secret = secret
        self.oauth = None
        self.ALLOWED_TRIES = allowed_tries
        self.AUTH_URL = 'https://id.twitch.tv/oauth2/token'
        self.logfile = path.join(log_path)
        self.reset_log()

    async def req_oauth(self, depth: int = 0):
        """Request oauth token from Twitch, return data as json"""
        loop = asyncio.get_running_loop()
        params = {'client_id': self.key, 'client_secret': self.secret, 'grant_type': 'client_credentials'}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.AUTH_URL, params=params) as resp:
                try:
                    resp.raise_for_status()
                except aiohttp.ClientResponseError as err:
                    if depth < self.ALLOWED_TRIES:
                        if err.status == 429:  # Too many requests
                            #resets_when = resp.headers.get('Ratelimit-Reset')
                            # no ratelimit-reset header in oauth requests
                            resets_when = time.time() + 60
                            self.logger.info(f"{id(loop)} REQ OAUTH Ratelimit - Waiting {round(float(resets_when) - time.time())}s"
                                             f" (until {resets_when}) for limit to reset")
                            while time.time() < float(resets_when):
                                await asyncio.sleep(1)
                            self.logger.info(f"{id(loop)} REQ OAUTH Ratelimit has been reset, retrying...")
                            return await self.req_oauth(depth=depth + 1)
                        else:
                            raise
                try:
                    data = await resp.json()
                except aiohttp.ContentTypeError:
                    self.logger.info(f"Twitch API with response {resp.status} did not return JSON: '{await resp.text()}'")
                    raise
                return data

    async def set_oauth(self):
        """Return oauth token from req_oauth if it gave valid data"""
        self.oauth = await self.req_oauth()
        self.oauth = self.oauth['access_token']
        return self

    def reset_log(self):
        with open(self.logfile, "w") as f:
            f.close()

    def log(self, yxyx: str, kind="a"):
        with open(self.logfile, kind) as f:
            f.write(str(datetime.utcnow()) + " " + yxyx + "\n")

    async def get(self, url: str, headers=None, wait_on_ratelimit: bool = True, depth: int = 0):
        if self.oauth is None:
            await self.set_oauth()
        if headers is None:
            headers = {'Client-ID': self.key, 'client_secret': self.secret, 'Authorization': f"Bearer {self.oauth}"}
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(url, headers=headers) as resp:
                self.usage_remaining = resp.headers.get('Ratelimit-Remaining')
                self.log(str(self.usage_remaining), "w")  # TODO create a mechanism to alert me thru discord if im getting close to ratelimit
                # & implement the manual locking (very similar to local_timestamps)
                try:
                    resp.raise_for_status()
                except aiohttp.ClientResponseError as err:
                    self.logger.info(f"HTTP error occurred: {err}")
                    if depth < self.ALLOWED_TRIES:
                        if err.status == 401:  # Unauthorized
                            self.logger.info("Unauthorized, resetting twitch auth")
                            await self.set_oauth()
                            return await self.get(url, depth=depth + 1)
                        elif err.status == 429:  # Too many requests
                            resets_when = resp.headers.get('Ratelimit-Reset')  # looks like '1685113410'
                            if wait_on_ratelimit:
                                self.logger.info(f"Ratelimit - Waiting {float(resets_when) - time.time()}s (until {resets_when}) for limit to reset")
                                while time.time() < float(resets_when):
                                    await asyncio.sleep(1)
                                self.logger.info("Ratelimit has been reset, retrying...")
                                return await self.get(url, depth=depth + 1)
                            else:
                                raise RateLimitExceededError(resets_when)
                        else:
                            raise
                    else:
                        raise TooManyTriesError
                return await resp.json()

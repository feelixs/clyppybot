from abc import ABC, abstractmethod
import logging


class BaseClip(ABC):
    """Base class for all clip types"""
    def __init__(self, slug):
        self.service = None
        self.url = None
        self.id = slug
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    async def download(self, filename):
        ...

import logging
import os
import subprocess
import concurrent.futures
import asyncio
from typing import Optional


SUPPORT_SERVER_URL = "https://discord.gg/Xts5YMUbeS"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1111723928604381314&permissions=182272&scope=bot%20applications.commands"
TOPGG_VOTE_LINK = "https://top.gg/bot/1111723928604381314/vote"


def create_nexus_str():
    return f"\n\n**[Invite CLYPPY]({INVITE_LINK}) | [Suggest a Feature]({SUPPORT_SERVER_URL}) | [Vote for me!]({TOPGG_VOTE_LINK})**"


class Tools:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def calculate_target_duration(self, filepath, target_size_mb=24.5):
        # Get current size in MB
        current_size_mb = os.path.getsize(filepath) / (1024 * 1024)

        # Get video duration using ffprobe
        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = await loop.run_in_executor(
                    pool,
                    lambda: subprocess.run([
                        'ffprobe',
                        '-v', 'error',
                        '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1',
                        filepath
                    ], capture_output=True, text=True)
                )

            if result.returncode != 0:
                return None

            current_duration_sec = float(result.stdout.strip())  # Added strip()
        except (ValueError, subprocess.SubprocessError) as e:
            self.logger.error(f"Error getting duration: {e}")
            return None

        # Calculate target duration
        mb_per_second = current_size_mb / current_duration_sec
        self.logger.info(f"Current size: {current_size_mb} MB, duration: {current_duration_sec} seconds, speed: {mb_per_second} MB/s")
        target_duration = target_size_mb / mb_per_second
        self.logger.info(f"Target duration: {target_duration} seconds")

        return target_duration

    async def trim_to_duration(self, input_file: str, target_duration: float) -> Optional[str]:
        """
        Trims video to target duration using ffmpeg
        Returns path to trimmed file or None if failed
        """
        output_file = input_file.replace('.mp4', '_trimmed.mp4')
        self.logger.info(f"Trimming {input_file}...")
        try:
            # Use ffmpeg to trim without re-encoding (-c copy)
            command = [
                'ffmpeg',
                '-i', input_file,
                '-t', str(target_duration),  # Duration to trim to
                '-c', 'copy',  # Copy streams without re-encoding
                '-y',  # Overwrite output if exists
                output_file
            ]

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await process.communicate()

            if process.returncode != 0:
                self.logger.error("Failed to trim video")
                return None

            # Remove original file
            os.remove(input_file)

            return output_file

        except Exception as e:
            self.logger.error(f"Error trimming video: {e}")
            return None

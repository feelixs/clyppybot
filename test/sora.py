import os
import asyncio
from typing import Optional
import aiohttp

from moviepy import VideoFileClip, concatenate_videoclips
from PIL import Image
from test.env import DEFAULT_PROMPT, get_ssl_context

LENGTH_DUR_SECONDS = 4


class SoraVideoExtender:
    """Handler for extending videos using OpenAI's Sora API"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Sora video extender

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")

        self.api_base = "https://api.openai.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def extract_last_frame(self, video_path: str, output_path: str = "temp_last_frame.png",
                                 target_size: tuple[int, int] = None) -> str:
        """
        Extract the last frame from a video file

        Args:
            video_path: Path to input video
            output_path: Where to save the extracted frame
            target_size: Optional (width, height) to resize frame to

        Returns:
            Path to saved frame image
        """
        print(f"Extracting last frame from {video_path}...")
        try:
            video = VideoFileClip(video_path)
            # Get frame 0.1 seconds before end to avoid potential blank frames
            last_frame_time = max(0, video.duration - 0.1)
            last_frame = video.get_frame(last_frame_time)

            # Convert numpy array to PIL Image
            img = Image.fromarray(last_frame.astype('uint8'))

            # Resize if target size specified
            if target_size:
                print(f"   Resizing frame from {img.size} to {target_size}")
                img = img.resize(target_size, Image.Resampling.LANCZOS)

            img.save(output_path)
            video.close()

            print(f"Last frame extracted to {output_path}")
            return output_path

        except Exception as e:
            print(f"Error extracting frame: {e}")
            raise

    async def generate_video_from_image(
            self,
            image_path: str,
            prompt: str = DEFAULT_PROMPT,
            duration: int = LENGTH_DUR_SECONDS,
            size: str = "1280x720"
    ) -> dict:
        """
        Generate a video from an image using Sora API

        Args:
            image_path: Path to the image (last frame of video)
            prompt: Description of how to extend/continue the video
            duration: Length of generated video in seconds
            size: Resolution (e.g., "1280x720", "1920x1080")

        Returns:
            Video generation response containing video ID and metadata
        """
        print(f"Generating video with Sora (duration: {duration}s)...")
        print(f"   Prompt: \"{prompt}\"")

        # Detect image type from file extension
        image_ext = os.path.splitext(image_path)[1].lower()
        mime_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp'
        }
        mime_type = mime_type_map.get(image_ext, 'image/png')

        # Prepare multipart form data
        form = aiohttp.FormData()
        form.add_field('prompt', prompt)
        form.add_field('model', 'sora-2-pro')
        form.add_field('size', size)
        form.add_field('seconds', str(duration))

        # Add image file
        with open(image_path, 'rb') as f:
            form.add_field(
                'input_reference',
                f,
                filename=os.path.basename(image_path),
                content_type=mime_type
            )

            # Submit generation request
            connector = aiohttp.TCPConnector(ssl=get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                # Remove Content-Type from headers as aiohttp sets it automatically for FormData
                headers = {k: v for k, v in self.headers.items() if k.lower() != 'content-type'}

                async with session.post(
                        f"{self.api_base}/videos",
                        data=form,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status in [200, 201]:
                        result = await response.json()
                        print(f"Video generation started (ID: {result.get('id', 'unknown')})")
                        return result
                    else:
                        error_text = await response.text()
                        raise Exception(f"API Error ({response.status}): {error_text}")

    async def wait_for_completion(
            self,
            video_id: str,
            max_wait_seconds: int = 300,
            check_interval: int = 5
    ) -> dict:
        """
        Poll for video generation completion

        Args:
            video_id: ID returned from generation request
            max_wait_seconds: Maximum time to wait (default: 5 minutes)
            check_interval: Seconds between status checks

        Returns:
            Completed video response with download URL
        """
        print(f"Waiting for video generation to complete...")
        elapsed = 0

        while elapsed < max_wait_seconds:
            connector = aiohttp.TCPConnector(ssl=get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                        f"{self.api_base}/videos/{video_id}",
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    status = result.get('status', 'unknown')

                    if status == 'completed':
                        print(f"Video generation completed!")
                        return result
                    elif status == 'failed':
                        error_msg = result.get('error', 'Unknown error')
                        raise Exception(f"Video generation failed: {error_msg}")

                    print(f"   Status: {status} (elapsed: {elapsed}s)")

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        raise TimeoutError(f"Video generation did not complete within {max_wait_seconds}s")

    async def download_video(self, url: str, output_path: str = "temp_generated_video.mp4") -> str:
        """
        Download the generated video from the provided URL

        Args:
            url: Download URL from Sora API response
            output_path: Where to save the downloaded video

        Returns:
            Path to downloaded video
        """
        print(f"Downloading generated video...")

        connector = aiohttp.TCPConnector(ssl=get_ssl_context())
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                if response.status == 200:
                    with open(output_path, 'wb') as f:
                        f.write(await response.read())
                    print(f"Video downloaded to {output_path}")
                    return output_path
                else:
                    raise Exception(f"Failed to download video: HTTP {response.status}")

    async def stitch_videos(
            self,
            original_video: str,
            generated_video: str,
            output_path: str = "extended_video.mp4"
    ) -> str:
        """
        Combine original video with generated extension

        Args:
            original_video: Path to original input video
            generated_video: Path to generated video from Sora
            output_path: Where to save the combined video

        Returns:
            Path to stitched video
        """
        print(f"Stitching videos together...")

        try:
            clip1 = VideoFileClip(original_video)
            clip2 = VideoFileClip(generated_video)

            # Ensure same resolution - resize generated video to match original
            if clip1.size != clip2.size:
                print(f"   Resizing generated video from {clip2.size} to {clip1.size}")
                clip2 = clip2.resize(clip1.size)  # type: ignore[attr-defined]

            # Ensure same fps
            if clip1.fps != clip2.fps:
                print(f"   Adjusting fps from {clip2.fps} to {clip1.fps}")
                clip2 = clip2.set_fps(clip1.fps)  # type: ignore[attr-defined]

            # Concatenate clips
            final_clip = concatenate_videoclips([clip1, clip2], method="compose")

            # Write output
            final_clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                verbose=False,
                logger=None
            )

            # Cleanup
            clip1.close()
            clip2.close()
            final_clip.close()

            print(f"Stitched video saved to {output_path}")
            return output_path

        except Exception as e:
            print(f"Error stitching videos: {e}")
            raise

    async def extend_video(
            self,
            input_video: str,
            output_path: str = "extended_video.mp4",
            prompt: str = DEFAULT_PROMPT
    ) -> str:
        """
        Main workflow: Extract last frame, generate extension, stitch together

        Args:
            input_video: Path to original video
            output_path: Path for final output
            prompt: Description for video extension

        Returns:
            Path to final stitched video
        """
        print(f"\n{'='*60}")
        print(f"Starting video extension workflow")
        print(f"{'='*60}\n")

        # Temporary file paths
        frame_path = "temp_last_frame.png"
        generated_video_path = "temp_generated_video.mp4"

        try:
            # Parse target size from generation parameters
            # Default to 1280x720, but could be made configurable
            target_size_str = "1280x720"
            width, height = map(int, target_size_str.split('x'))

            # Step 1: Extract last frame and resize to match target dimensions
            await self.extract_last_frame(input_video, frame_path, target_size=(width, height))

            # Step 2: Generate video from frame
            generation_response = await self.generate_video_from_image(
                frame_path,
                prompt=prompt,
                duration=LENGTH_DUR_SECONDS,
                size=target_size_str
            )

            video_id = generation_response.get('id')
            if not video_id:
                raise Exception("No video ID returned from API")

            # Step 3: Wait for completion
            completed = await self.wait_for_completion(video_id)

            # Step 4: Download generated video
            video_url = completed.get('url')
            if not video_url:
                raise Exception("No download URL in completed response")

            await self.download_video(video_url, generated_video_path)

            # Step 5: Stitch videos together
            final_video = await self.stitch_videos(
                input_video,
                generated_video_path,
                output_path
            )

            print(f"\n{'='*60}")
            print(f"SUCCESS! Extended video saved to: {final_video}")
            print(f"{'='*60}\n")

            return final_video

        except Exception as e:
            print(f"\nError during video extension: {e}")
            raise

        finally:
            # Cleanup temporary files
            for temp_file in [frame_path, generated_video_path]:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        print(f"Cleaned up {temp_file}")
                    except Exception as e:
                        print(f"Could not remove {temp_file}: {e}")


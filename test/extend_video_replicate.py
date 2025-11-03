#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Replicate Video Extension Script (Stable Video Diffusion)

Takes an input video, extracts the last frame, sends it to Replicate's
Stable Video Diffusion API to generate a continuation, then stitches
the original and generated videos together.

Usage:
    python replicate.py input_video.mp4 [--output extended_video.mp4] [--prompt "custom prompt"]
"""
import asyncio
import os
import sys
import argparse
from typing import Optional

from moviepy import VideoFileClip, concatenate_videoclips
from PIL import Image
from replicate import Client


# Global configuration
LENGTH_DUR_SECONDS = 4  # Stable Video Diffusion typically generates 2-4 second clips
DEFAULT_PROMPT = "smooth continuation with natural movement and consistent visual style"


class ReplicateVideoExtender:
    """Handler for extending videos using Replicate's Stable Video Diffusion"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Replicate video extender

        Args:
            api_key: Replicate API key (defaults to REPLICATE_API_TOKEN env var)
        """
        self.api_key = api_key or os.getenv('REPLICATE_API_TOKEN')
        if not self.api_key:
            raise ValueError("Replicate API key not found. Set REPLICATE_API_TOKEN environment variable.")

        # Initialize the Replicate client
        self.client = Client(api_token=self.api_key)

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
        motion_bucket_id: int = 127,
        fps: int = 6,
        model: str = "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438"
    ) -> str:
        """
        Generate a video from an image using Replicate's Stable Video Diffusion

        Args:
            image_path: Path to the image (last frame of video)
            prompt: Description of motion/continuation (note: SVD has limited prompt influence)
            motion_bucket_id: Controls amount of motion (1-255, higher = more motion)
            fps: Frames per second for output video
            model: Replicate model version to use

        Returns:
            URL of generated video
        """
        print(f"Generating video with Stable Video Diffusion...")
        print(f"   Motion intensity: {motion_bucket_id}/255")
        print(f"   FPS: {fps}")

        try:
            # Open the image file
            with open(image_path, 'rb') as f:
                # Run the model using the client
                output = self.client.run(
                    model,
                    input={
                        "input_image": f,
                        "motion_bucket_id": motion_bucket_id,
                        "fps": fps,
                        "cond_aug": 0.02,  # Conditioning augmentation (noise added to input)
                    }
                )

            # Output is typically a URL to the generated video
            print(f"Raw output type: {type(output)}")
            print(f"Raw output value: {output}")

            if isinstance(output, str):
                video_url = output
            elif isinstance(output, list) and len(output) > 0:
                video_url = output[0]
            elif hasattr(output, 'url'):
                video_url = output.url
            else:
                # Just try to convert to string as fallback
                video_url = str(output)

            print(f"Video generation completed!")
            print(f"   Video URL: {video_url}")
            return video_url

        except Exception as e:
            print(f"Error generating video: {e}")
            raise

    async def download_video(self, url: str, output_path: str = "temp_generated_video.mp4") -> str:
        """
        Download the generated video from the provided URL

        Args:
            url: Download URL from Replicate response
            output_path: Where to save the downloaded video

        Returns:
            Path to downloaded video
        """
        print(f"Downloading generated video...")

        try:
            import urllib.request
            import ssl
            import certifi

            # Create SSL context with certifi certificates
            ssl_context = ssl.create_default_context(cafile=certifi.where())

            # Download using urlopen with SSL context
            with urllib.request.urlopen(url, context=ssl_context) as response:
                with open(output_path, 'wb') as out_file:
                    out_file.write(response.read())

            print(f"Video downloaded to {output_path}")
            return output_path

        except Exception as e:
            print(f"Error downloading video: {e}")
            raise

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
            generated_video: Path to generated video from Replicate
            output_path: Where to save the combined video

        Returns:
            Path to stitched video
        """
        print(f"Stitching videos together...")

        try:
            from moviepy import vfx

            clip1 = VideoFileClip(original_video)
            clip2 = VideoFileClip(generated_video)

            # Ensure same resolution - resize generated video to match original
            if clip1.size != clip2.size:
                print(f"   Resizing generated video from {clip2.size} to {clip1.size}")
                clip2 = vfx.Resize(new_size=clip1.size).apply(clip2)

            # Ensure same fps
            if clip1.fps != clip2.fps:
                print(f"   Adjusting fps from {clip2.fps} to {clip1.fps}")
                clip2 = clip2.with_fps(clip1.fps)

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
        prompt: str = DEFAULT_PROMPT,
        motion_bucket_id: int = 127
    ) -> str:
        """
        Main workflow: Extract last frame, generate extension, stitch together

        Args:
            input_video: Path to original video
            output_path: Path for final output
            prompt: Description for video extension (limited influence in SVD)
            motion_bucket_id: Controls amount of motion (1-255, higher = more motion)

        Returns:
            Path to final stitched video
        """
        print(f"\n{'='*60}")
        print(f"Starting video extension workflow (Replicate/SVD)")
        print(f"{'='*60}\n")

        # Temporary file paths
        frame_path = "temp_last_frame_replicate.png"
        generated_video_path = "temp_generated_video_replicate.mp4"

        try:
            # Step 1: Extract last frame (SVD works best with 1024x576 or similar)
            await self.extract_last_frame(input_video, frame_path, target_size=(1024, 576))

            # Step 2: Generate video from frame
            video_url = await self.generate_video_from_image(
                frame_path,
                prompt=prompt,
                motion_bucket_id=motion_bucket_id
            )

            # Step 3: Download generated video
            await self.download_video(video_url, generated_video_path)

            # Step 4: Stitch videos together
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


async def main():
    """Command-line interface for video extension"""
    parser = argparse.ArgumentParser(
        description="Extend a video using Replicate's Stable Video Diffusion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python replicate.py my_video.mp4
  python replicate.py input.mp4 --output result.mp4
  python replicate.py clip.mp4 --motion 180 --prompt "fast camera movement"
        """
    )

    parser.add_argument(
        'input_video',
        type=str,
        help='Path to input video file'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        default='extended_video.mp4',
        help='Path for output video (default: extended_video.mp4)'
    )

    parser.add_argument(
        '--prompt', '-p',
        type=str,
        default=DEFAULT_PROMPT,
        help='Custom prompt for video generation (limited influence in SVD)'
    )

    parser.add_argument(
        '--motion', '-m',
        type=int,
        default=127,
        help='Motion intensity (1-255, default: 127). Higher = more motion'
    )

    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='Replicate API key (defaults to REPLICATE_API_TOKEN env var)'
    )

    args = parser.parse_args()

    # Validate input file exists
    if not os.path.exists(args.input_video):
        print(f"Error: Input video not found: {args.input_video}")
        sys.exit(1)

    # Validate motion bucket ID
    if not 1 <= args.motion <= 255:
        print(f"Error: Motion intensity must be between 1 and 255")
        sys.exit(1)

    try:
        # Initialize extender
        extender = ReplicateVideoExtender(api_key=args.api_key)

        # Run extension workflow
        result = await extender.extend_video(
            input_video=args.input_video,
            output_path=args.output,
            prompt=args.prompt,
            motion_bucket_id=args.motion
        )

        print(f"\n✓ All done! Your extended video is ready at: {result}")

    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

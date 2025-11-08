#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Video Extension Script with AI-Generated Prompts

Takes an input video, extracts 5 frames from the last 5 seconds, uses OpenAI's
Vision API to analyze the scene and generate an optimal continuation prompt,
then uses Replicate's Stable Video Diffusion to extend the video.

Usage:
    python extend_video_smart.py input_video.mp4 [--output extended_video.mp4]
"""

from moviepy import VideoFileClip, concatenate_videoclips, vfx
from typing import Optional, List
from google.genai import types
from replicate import Client
from runwayml import RunwayML
from google import genai
from PIL import Image
import mimetypes
import argparse
import os
import sys
import base64
import asyncio
import aiohttp
import ssl
import certifi
import time
import json


# Gemini video analysis prompt for continuation prediction with frame selection
GEMINI_VIDEO_ANALYSIS_PROMPT = """You are analyzing the LAST 5 SECONDS of a video to accomplish two goals:
1. Select the BEST FRAME for starting video generation
2. Predict what happens NEXT after that frame

PART 1 - SELECT BEST FRAME TIMESTAMP (0-5 seconds):

FRAME SELECTION PRIORITY:
- Use the LAST frame (closest to 5 seconds) if it has clear visual content and context
- If the last frame is blank, blurry, or lacks content, select the frame CLOSEST to the end that has good visual content
- Prefer frames as late as possible in the timeline while ensuring quality

AVOID frames that are:
- Black, faded, or in transition
- Blurry or mid-fast-motion
- At scene cuts or shot changes
- Showing ending cues (fadeouts, people leaving)
- Blank or lacking visual information

PREFER frames that are:
- Clear, stable, and well-lit
- As close to the end (5 seconds) as possible
- Show continuous action that can be extended
- Have good visual content and composition

PART 2 - ANALYZE FOR CONTINUATION:

Consider VISUAL cues:
- Object/person movement patterns and trajectories
- Camera movement (pan, tilt, zoom, static)
- Motion speed and direction

Consider AUDIO cues:
- Sound patterns (music, speech, ambient noise)
- Audio dynamics (fade-ins, crescendos, etc.)
- Dialogue or narrative direction
- Emotional tone

TEMPORAL ANALYSIS:
- How are things changing over time?
- What motion patterns suggest natural continuation?
- Audio-visual correlations (footsteps + walking, music + action)

OUTPUT FORMAT (JSON only):
{
  "timestamp_sec": <number 0-5>,
  "prompt": "<1-2 sentences describing what happens NEXT>"
}

Example:
{
  "timestamp_sec": 4.8,
  "prompt": "Camera continues panning left as person walks toward the building entrance"
}"""


def get_ssl_context():
    """Create SSL context using certifi certificates"""
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return ssl_context


class SmartVideoExtender:
    """Handler for extending videos using AI-analyzed prompts and Replicate's Stable Video Diffusion"""
    def __init__(self, openai_api_key: Optional[str] = None, replicate_api_key: Optional[str] = None,
                 runway_api_key: Optional[str] = None, google_api_key: Optional[str] = None, model: str = "replicate"):
        """
        Initialize the smart video extender

        Args:
            openai_api_key: OpenAI API key (defaults to MY_OWN_OPENAI_API_KEY env var)
            replicate_api_key: Replicate API key (defaults to REPLICATE_API_TOKEN env var, only needed if model="replicate")
            runway_api_key: Runway API key (defaults to RUNWAYML_API_SECRET env var, only needed if model="runway")
            google_api_key: Google API key (defaults to GOOGLE_API_KEY env var, only needed if model="veo")
            model: Which model to use for video generation ("replicate", "sora", "runway", or "veo")
        """
        self.openai_api_key = openai_api_key or os.getenv('MY_OWN_OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not found. Set MY_OWN_OPENAI_API_KEY environment variable.")

        self.model = model.lower()

        # Always initialize Google Gemini client for video analysis (regardless of generation model)
        google_key = google_api_key or os.getenv('GOOGLE_API_KEY')
        if google_key:
            self.veo_client = genai.Client(api_key=google_key)
            print(f"Gemini client initialized for video analysis")
        else:
            self.veo_client = None
            print("Warning: No GOOGLE_API_KEY found. Will fall back to frame-based analysis.")

        # Initialize video generation model clients
        if self.model == "replicate":
            self.replicate_api_key = replicate_api_key or os.getenv('REPLICATE_API_TOKEN')
            if not self.replicate_api_key:
                raise ValueError("Replicate API key not found. Set REPLICATE_API_TOKEN environment variable.")
            # Initialize the Replicate client
            self.replicate_client = Client(api_token=self.replicate_api_key)
        elif self.model == "runway":
            runway_key = runway_api_key or os.getenv('RUNWAYML_API_SECRET')
            if runway_key:
                os.environ['RUNWAYML_API_SECRET'] = runway_key
            self.runway_client = RunwayML()
        elif self.model == "veo":
            if not google_key:
                raise ValueError("Google API key not found. Set GOOGLE_API_KEY environment variable for Veo generation.")

        self.openai_api_base = "https://api.openai.com/v1"
        self.openai_headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }

    @staticmethod
    async def extract_multiple_frames(
        video_path: str,
        num_frames: int = 5,
        target_size: tuple[int, int] = (512, 512)
    ) -> List[str]:
        """
        Extract multiple frames from the end of a video

        Args:
            video_path: Path to input video
            num_frames: Number of frames to extract (from last N seconds)
            target_size: Size to resize frames to

        Returns:
            List of paths to saved frame images
        """
        print(f"Extracting {num_frames} frames from the last {num_frames} seconds...")
        frame_paths = []
        try:
            video = VideoFileClip(video_path)
            duration = video.duration

            for i in range(num_frames):
                # Extract frames at t-4, t-3, t-2, t-1, t-0 seconds from the end (chronological order)
                frame_time = max(0, duration - (num_frames - i) - 0.1)
                frame = video.get_frame(frame_time)

                # Convert to PIL Image
                img = Image.fromarray(frame.astype('uint8'))

                # Resize for vision API (smaller = cheaper, but still detailed enough)
                print(f"   Frame {i+1}: Resizing from {img.size} to {target_size}")
                img = img.resize(target_size, Image.Resampling.LANCZOS)

                # Save frame
                frame_path = f"temp_frame_{i}.png"
                img.save(frame_path)
                frame_paths.append(frame_path)

            video.close()
            print(f"Extracted {len(frame_paths)} frames successfully")
            return frame_paths

        except Exception as e:
            print(f"Error extracting frames: {e}")
            raise

    @staticmethod
    async def extract_last_clip(
        video_path: str,
        duration: int = 10,
        output_path: str = "temp_last_clip.mp4"
    ) -> str:
        """
        Extract the last N seconds of video as a separate clip (preserves audio)

        Args:
            video_path: Path to input video
            duration: Seconds to extract from end (default: 10)
            output_path: Where to save the clip

        Returns:
            Path to extracted clip
        """
        print(f"Extracting last {duration} seconds of video for analysis...")
        try:
            video = VideoFileClip(video_path)
            video_duration = video.duration

            # Calculate start time (at least 0)
            start_time = max(0, video_duration - duration)

            # Extract subclip with audio
            clip = video.subclipped(start_time, video_duration)

            # Save with audio preserved
            clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                logger=None
            )

            video.close()
            clip.close()

            print(f"Extracted {duration}s clip to {output_path}")
            return output_path

        except Exception as e:
            print(f"Error extracting clip: {e}")
            raise

    @staticmethod
    async def encode_image_to_base64(image_path: str) -> str:
        """
        Encode an image file to base64 data URL

        Args:
            image_path: Path to image file

        Returns:
            Base64-encoded data URL
        """
        with open(image_path, 'rb') as f:
            image_data = f.read()
            base64_image = base64.b64encode(image_data).decode('utf-8')
            return f"data:image/png;base64,{base64_image}"

    async def analyze_frames_with_vision(self, frame_paths: List[str]) -> str:
        """
        Use OpenAI Vision API to analyze frames and generate a continuation prompt

        Args:
            frame_paths: List of paths to frame images

        Returns:
            AI-generated prompt for video continuation
        """
        print(f"\nAnalyzing {len(frame_paths)} frames with OpenAI Vision API...")
        try:
            # Encode all frames to base64 (already in chronological order)
            image_contents = []
            for i, frame_path in enumerate(frame_paths):
                base64_image = await self.encode_image_to_base64(frame_path)
                image_contents.append({
                    "type": "image_url",
                    "image_url": {
                        "url": base64_image,
                        "detail": "low"  # Use low detail for cost efficiency
                    }
                })

            # Prepare the vision API request
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """You are analyzing 5 frames from the last 5 seconds of a video (shown in chronological order, oldest to newest).

Based on what HAS HAPPENED in these frames, predict what should happen NEXT in the video continuation.

Your task:
1. Observe the motion trajectory, speed, and direction from the sequence
2. Identify what subjects/objects are doing and where they're heading
3. Note camera movement patterns if any
4. Based on this progression, write a SHORT prompt (1-2 sentences max) describing what happens NEXT

The prompt should predict the CONTINUATION, not describe what already happened.

Example analysis: "Person walking left to right across frame" → Good prompt: "Person continues walking right and exits frame"

Your response should ONLY be the continuation prompt itself, nothing else. Be concise and specific about the NEXT action."""
                        }
                    ] + image_contents
                }
            ]

            payload = {
                "model": "gpt-4o",  # Use gpt-4o which supports vision
                "messages": messages,
                "max_tokens": 150,
                "temperature": 0.7
            }

            # Make API request
            connector = aiohttp.TCPConnector(ssl=get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    f"{self.openai_api_base}/chat/completions",
                    headers=self.openai_headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        generated_prompt = result['choices'][0]['message']['content'].strip()
                        print(f"\n✓ AI-Generated Prompt:")
                        print(f"  \"{generated_prompt}\"\n")
                        return generated_prompt
                    else:
                        error_text = await response.text()
                        raise Exception(f"Vision API Error ({response.status}): {error_text}")

        except Exception as e:
            print(f"Error analyzing frames: {e}")
            raise

    async def analyze_video_with_gemini(
        self,
        video_path: str,
        duration_to_analyze: int = 5,
        model: str = "gemini-2.0-flash-exp"
    ) -> dict:
        """
        Analyze video with Gemini for video+audio understanding and frame selection

        Args:
            video_path: Path to video file (or clip)
            duration_to_analyze: Seconds to extract from end (default: 5)
            model: Gemini model to use (default: gemini-2.0-flash-exp)

        Returns:
            dict: {"prompt": str, "timestamp_sec": float}
        """
        print(f"\nAnalyzing video with {model} (video+audio)...")

        temp_clip_path = None
        uploaded_file = None

        try:
            # Step 1: Extract last N seconds
            temp_clip_path = await self.extract_last_clip(
                video_path,
                duration=duration_to_analyze,
                output_path="temp_gemini_analysis_clip.mp4"
            )

            # Step 2: Upload video file
            print("   Uploading video to Gemini...")
            uploaded_file = self.veo_client.files.upload(file=temp_clip_path)
            print(f"   File uploaded: {uploaded_file.name}")

            # Step 3: Wait for processing
            print("   Waiting for video processing...")
            max_wait = 60  # 1 minute max for short clips
            elapsed = 0

            while elapsed < max_wait:
                uploaded_file = self.veo_client.files.get(name=uploaded_file.name)

                if uploaded_file.state.name == "ACTIVE":
                    print("   Video ready for analysis!")
                    break
                elif uploaded_file.state.name == "FAILED":
                    raise Exception(f"Video processing failed: {uploaded_file.state}")

                print(f"   Processing... ({elapsed}s)")
                await asyncio.sleep(5)
                elapsed += 5

            if uploaded_file.state.name != "ACTIVE":
                raise TimeoutError("Video processing did not complete in time")

            # Step 4: Analyze with Gemini using structured JSON output
            print("   Generating continuation prompt and frame selection...")

            # Configure structured JSON output
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema={
                    "type": "object",
                    "properties": {
                        "timestamp_sec": {
                            "type": "number",
                            "description": "Timestamp in seconds (0-5) of best frame"
                        },
                        "prompt": {
                            "type": "string",
                            "description": "1-2 sentence description of what happens next"
                        }
                    },
                    "required": ["timestamp_sec", "prompt"]
                }
            )

            response = self.veo_client.models.generate_content(
                model=model,
                contents=[
                    uploaded_file,
                    GEMINI_VIDEO_ANALYSIS_PROMPT
                ],
                config=config
            )

            result = json.loads(response.text)

            print(f"\n✓ Gemini Analysis Result:")
            print(f"  Best frame at: {result['timestamp_sec']:.2f}s")
            print(f"  Prompt: \"{result['prompt']}\"\n")

            return result

        except Exception as e:
            print(f"Error analyzing video with Gemini: {e}")
            raise

        finally:
            # Cleanup: Delete uploaded file
            if uploaded_file:
                try:
                    self.veo_client.files.delete(name=uploaded_file.name)
                    print(f"   Cleaned up uploaded file: {uploaded_file.name}")
                except Exception as e:
                    print(f"   Warning: Could not delete file: {e}")

            # Cleanup: Remove temporary clip
            if temp_clip_path and os.path.exists(temp_clip_path):
                try:
                    os.remove(temp_clip_path)
                    print(f"   Cleaned up temp clip: {temp_clip_path}")
                except Exception as e:
                    print(f"   Warning: Could not remove temp clip: {e}")

    @staticmethod
    async def extract_last_frame(
        video_path: str,
        output_path: str = "temp_last_frame.png",
        target_size: tuple[int, int] = None
    ) -> str:
        """
        Extract the last frame from a video file (for video generation)

        Args:
            video_path: Path to input video
            output_path: Where to save the extracted frame
            target_size: Optional (width, height) to resize frame to

        Returns:
            Path to saved frame image
        """
        print(f"Extracting last frame for video generation...")
        try:
            video = VideoFileClip(video_path)
            print(f"   Video duration: {video.duration:.2f}s, FPS: {video.fps}")

            # Use subclip to get just the last second, then iterate to get the very last frame
            # This is much faster than iterating the whole video
            last_second_start = max(0, video.duration - 1.0)
            last_second_clip = video.subclipped(last_second_start, video.duration)

            last_frame = None
            frame_count = 0
            for frame in last_second_clip.iter_frames(fps=video.fps, dtype='uint8'):
                last_frame = frame
                frame_count += 1

            last_second_clip.close()

            if last_frame is None:
                # Fallback to get_frame if iteration fails
                print("   Warning: iteration failed, using get_frame fallback")
                last_frame = video.get_frame(video.duration - 0.01)
            else:
                print(f"   Iterated {frame_count} frames from last second")
            print(f"   Frame shape: {last_frame.shape}")
            img = Image.fromarray(last_frame.astype('uint8'))
            print(f"   Image size before resize: {img.size}")

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

    @staticmethod
    async def extract_frame_at_timestamp(
        video_path: str,
        timestamp_sec: float,
        output_path: str = "temp_selected_frame.png",
        target_size: tuple[int, int] = None
    ) -> str:
        """
        Extract frame at specific timestamp from video

        Args:
            video_path: Path to input video
            timestamp_sec: Timestamp in seconds (e.g., 3.5)
            output_path: Where to save the extracted frame
            target_size: Optional (width, height) to resize frame to

        Returns:
            Path to saved frame image
        """
        print(f"Extracting frame at timestamp {timestamp_sec:.2f}s...")
        try:
            video = VideoFileClip(video_path)

            # Clamp timestamp to valid range
            timestamp_sec = max(0, min(timestamp_sec, video.duration - 0.01))
            print(f"   Using timestamp: {timestamp_sec:.2f}s (video duration: {video.duration:.2f}s)")

            # Extract frame at timestamp
            frame = video.get_frame(timestamp_sec)
            img = Image.fromarray(frame.astype('uint8'))
            print(f"   Frame shape: {frame.shape}")
            print(f"   Image size before resize: {img.size}")

            if target_size:
                print(f"   Resizing frame from {img.size} to {target_size}")
                img = img.resize(target_size, Image.Resampling.LANCZOS)

            img.save(output_path)
            video.close()
            print(f"Frame extracted to {output_path}")
            return output_path

        except Exception as e:
            print(f"Error extracting frame at timestamp: {e}")
            raise

    async def generate_video_with_sora(
        self,
        image_path: str,
        prompt: str,
        duration: int = 8,
        size: str = "1280x720"
    ) -> str:
        """
        Generate a video from an image using OpenAI's Sora API

        Args:
            image_path: Path to the image (last frame of video)
            prompt: AI-generated description of continuation
            duration: Length of generated video in seconds (4, 8, or 12)
            size: Resolution (e.g., "1280x720", "1920x1080")

        Returns:
            Video ID for polling
        """
        print(f"Generating video with Sora (duration: {duration}s)...")
        print(f"   Using prompt: \"{prompt}\"")

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
        form.add_field('model', 'sora-2')
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
                headers = {k: v for k, v in self.openai_headers.items() if k.lower() != 'content-type'}
                async with session.post(
                    f"{self.openai_api_base}/videos",
                    data=form,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status in [200, 201]:
                        result = await response.json()
                        video_id = result.get('id')
                        print(f"Video generation started (ID: {video_id})")
                        return video_id
                    else:
                        error_text = await response.text()
                        raise Exception(f"Sora API Error ({response.status}): {error_text}")

    async def wait_for_sora_completion(
        self,
        video_id: str,
        max_wait_seconds: int = 300,
        check_interval: int = 5
    ) -> str:
        """
        Poll for Sora video generation completion

        Args:
            video_id: ID returned from generation request
            max_wait_seconds: Maximum time to wait (default: 5 minutes)
            check_interval: Seconds between status checks

        Returns:
            Video ID upon completion
        """
        print(f"Waiting for Sora video generation to complete...")
        elapsed = 0
        while elapsed < max_wait_seconds:
            connector = aiohttp.TCPConnector(ssl=get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    f"{self.openai_api_base}/videos/{video_id}",
                    headers=self.openai_headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    status = result.get('status', 'unknown')
                    if status == 'completed':
                        print(f"Video generation completed!")
                        # Return the video_id, which will be used to construct the content download URL
                        return video_id
                    elif status == 'failed':
                        error_msg = result.get('error', 'Unknown error')
                        raise Exception(f"Video generation failed: {error_msg}")

                    print(f"   Status: {status} (elapsed: {elapsed}s)")

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        raise TimeoutError(f"Video generation did not complete within {max_wait_seconds}s")

    async def generate_video_with_replicate(
        self,
        image_path: str,
        prompt: str,
        motion_bucket_id: int = 127,
        fps: int = 6,
        replicate_model: str = "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438"
    ) -> str:
        """
        Generate a video from an image using Replicate's Stable Video Diffusion

        Args:
            image_path: Path to the image (last frame of video)
            prompt: AI-generated description of continuation
            motion_bucket_id: Controls amount of motion (1-255, higher = more motion)
            fps: Frames per second for output video
            replicate_model: Replicate model version to use

        Returns:
            URL of generated video
        """
        print(f"Generating video with Stable Video Diffusion...")
        print(f"   Using prompt: \"{prompt}\"")
        print(f"   Motion intensity: {motion_bucket_id}/255")
        print(f"   FPS: {fps}")
        try:
            with open(image_path, 'rb') as f:
                output = self.replicate_client.run(
                    replicate_model,
                    input={
                        "input_image": f,
                        "motion_bucket_id": motion_bucket_id,
                        "fps": fps,
                        "cond_aug": 0.02,
                    }
                )

            # Parse output
            if isinstance(output, str):
                video_url = output
            elif isinstance(output, list) and len(output) > 0:
                video_url = output[0]
            elif hasattr(output, 'url'):
                video_url = output.url
            else:
                video_url = str(output)

            print(f"Video generation completed!")
            print(f"   Video URL: {video_url}")
            return video_url

        except Exception as e:
            print(f"Error generating video: {e}")
            raise

    async def generate_video_with_runway(
        self,
        image_path: str,
        prompt: str,
        duration: int = 10,
        model: str = 'gen4_turbo'
    ) -> str:
        """
        Generate a video from an image using Runway's Gen-4 Turbo

        Args:
            image_path: Path to the image (last frame of video)
            prompt: AI-generated description of continuation
            duration: Length of generated video in seconds (max 10)
            model: Runway model to use (default: gen4_turbo)

        Returns:
            URL of generated video
        """
        print(f"Generating video with Runway {model}...")
        print(f"   Using prompt: \"{prompt}\"")
        print(f"   Duration: {duration}s")
        try:
            # Upload the image and get a URL (Runway expects a URL)
            # For now, we'll use the file path directly if it's accessible
            # In production, you'd upload to a temporary URL
            with open(image_path, 'rb') as f:
                image_data = f.read()
                # Encode to base64 data URL
                b64_image = base64.b64encode(image_data).decode('utf-8')
                image_url = f"data:image/png;base64,{b64_image}"

            # Create the video generation task
            # Runway requires a specific ratio: "1280:720", "720:1280", "1104:832", "832:1104", "960:960", "1584:672"
            task = self.runway_client.image_to_video.create(
                model=model,
                prompt_image=image_url,
                prompt_text=prompt,
                duration=duration,
                ratio="1280:720"  # Standard 16:9 widescreen
            ).wait_for_task_output()
            if task.status == "SUCCEEDED" and task.output:
                video_url = task.output[0] if isinstance(task.output, list) else task.output
                print(f"Video generation completed!")
                print(f"   Video URL: {video_url}")
                return video_url
            else:
                failure_reason = getattr(task, 'failure', 'Unknown error')
                raise Exception(f"Runway task failed: {failure_reason}")

        except Exception as e:
            print(f"Error generating video with Runway: {e}")
            raise

    async def generate_video_with_veo(
        self,
        image_path: str,
        prompt: str,
        duration: int = 8,
        model: str = 'veo-3.0-fast-generate-001'
    ) -> str:
        """
        Generate a video from an image using Google Veo 3 Fast (with native audio!)

        Args:
            image_path: Path to the image (last frame of video)
            prompt: AI-generated description of continuation
            duration: Length of generated video in seconds (default: 8)
            model: Veo model to use (default: veo-3.0-fast-generate-001, $0.15/sec)

        Returns:
            Path to downloaded video file
        """
        print(f"Generating video with Google {model}...")
        print(f"   Using prompt: \"{prompt}\"")
        print(f"   Duration: {duration}s")
        print(f"   Audio: Native audio generation enabled!")
        try:
            # Load the image bytes
            with open(image_path, 'rb') as f:
                image_bytes = f.read()

            # Determine MIME type
            mime_type = mimetypes.guess_type(image_path)[0] or 'image/png'

            # Create Image object for Veo
            image_obj = types.Image(
                image_bytes=image_bytes,
                mime_type=mime_type
            )

            # Generate video with Veo 3.1
            print("   Submitting video generation request...")

            # Create config with personGeneration parameter
            config = types.GenerateVideosConfig(
                person_generation="allow_adult"  # Allow generation of people for image-to-video
            )
            operation = self.veo_client.models.generate_videos(
                model=model,
                prompt=prompt,
                image=image_obj,
                config=config,
            )

            # Poll the operation status until the video is ready
            print("   Waiting for video generation to complete...")
            max_wait = 600  # 10 minutes max
            elapsed = 0
            poll_interval = 10
            while not operation.done and elapsed < max_wait:
                print(f"   Status: In progress (elapsed: {elapsed}s)")
                time.sleep(poll_interval)
                elapsed += poll_interval
                operation = self.veo_client.operations.get(operation)

            if not operation.done:
                raise TimeoutError(f"Video generation did not complete within {max_wait}s")

            # Download the video
            print("   Video generation completed! Downloading...")

            # Check if response exists and handle moderation blocks
            if not operation.response or not hasattr(operation.response, 'generated_videos'):
                raise Exception(f"No video in response: {operation.response}")

            # Check for content moderation
            filtered_count = getattr(operation.response, 'rai_media_filtered_count', None)
            if filtered_count and filtered_count > 0:
                reasons = operation.response.rai_media_filtered_reasons
                raise Exception(f"Video blocked by content moderation: {reasons}")

            if not operation.response.generated_videos:
                raise Exception(f"No videos generated. Response: {operation.response}")

            video = operation.response.generated_videos[0]

            # Save to temporary file
            temp_video_path = "temp_veo_video.mp4"

            # Download the video file
            video_file = video.video
            downloaded_data = self.veo_client.files.download(file=video_file)

            # Validate downloaded data is actually video, not error content
            if not downloaded_data or len(downloaded_data) < 100:
                raise ValueError(f"Downloaded data is too small ({len(downloaded_data)} bytes), likely not a valid video")

            # Check for video file signature (magic bytes)
            # MP4 files should contain 'ftyp' box near the beginning
            if b'ftyp' not in downloaded_data[:200]:
                # Check if it's an error message (HTML/JSON)
                if b'<!DOCTYPE' in downloaded_data[:200] or b'<html' in downloaded_data[:200].lower():
                    raise ValueError("Veo returned HTML instead of video - likely an error page")
                if b'{' in downloaded_data[:10] and b'"error"' in downloaded_data[:500]:
                    raise ValueError("Veo returned JSON error instead of video")
                # Warn but continue if we can't identify the format
                print(f"   WARNING: Downloaded data doesn't have expected MP4 signature")

            # Write to file
            with open(temp_video_path, 'wb') as f:
                f.write(downloaded_data)

            print(f"   Video downloaded successfully with audio! ({len(downloaded_data)} bytes)")
            return temp_video_path

        except Exception as e:
            print(f"Error generating video with Veo: {e}")
            raise

    async def generate_video_from_image(
        self,
        image_path: str,
        prompt: str,
        motion_bucket_id: int = 127,
        duration: int = 8
    ) -> tuple[str, bool]:
        """
        Generate a video from an image using the configured model

        Args:
            image_path: Path to the image (last frame of video)
            prompt: AI-generated description of continuation
            motion_bucket_id: Controls amount of motion for Replicate (1-255)
            duration: Duration in seconds

        Returns:
            Tuple of (video_url_or_path, is_local_file)
        """
        if self.model == "sora":
            video_id = await self.generate_video_with_sora(image_path, prompt, duration=duration)
            completed_video_id = await self.wait_for_sora_completion(video_id)
            video_url = f"{self.openai_api_base}/videos/{completed_video_id}/content"
            return video_url, False
        elif self.model == "runway":
            video_url = await self.generate_video_with_runway(image_path, prompt, duration=duration)
            return video_url, False
        elif self.model == "veo":
            video_path = await self.generate_video_with_veo(image_path, prompt, duration=duration)
            return video_path, True
        else:  # replicate
            video_url = await self.generate_video_with_replicate(image_path, prompt, motion_bucket_id=motion_bucket_id)
            return video_url, False

    @staticmethod
    async def download_video(
            url: str,
            output_path: str = "temp_generated_video.mp4",
            headers: Optional[dict] = None
    ) -> str:
        """
        Download the generated video from the provided URL

        Args:
            url: Download URL
            output_path: Where to save the downloaded video
            headers: Optional headers for the request

        Returns:
            Path to downloaded video
        """
        print(f"Downloading generated video from {url}...")
        try:
            connector = aiohttp.TCPConnector(ssl=get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    response.raise_for_status()

                    # Validate content-type to ensure we're downloading a video, not an error page
                    content_type = response.headers.get('Content-Type', '').lower()
                    print(f"   Content-Type: {content_type}")

                    # Check for video content types
                    valid_video_types = ['video/mp4', 'video/mpeg', 'video/quicktime', 'application/octet-stream']
                    is_valid = any(vtype in content_type for vtype in valid_video_types)

                    if not is_valid and content_type:
                        # Check if it's HTML (error page)
                        if 'text/html' in content_type or 'application/json' in content_type:
                            raise ValueError(f"Server returned {content_type} instead of video. This is likely an error page.")
                        # Warn but continue for unknown types
                        print(f"   WARNING: Unexpected content-type '{content_type}', expected video format")

                    # Download the content
                    downloaded_bytes = b''
                    with open(output_path, 'wb') as out_file:
                        while True:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            out_file.write(chunk)
                            downloaded_bytes += chunk

                    # Validate the downloaded content (check magic bytes)
                    if len(downloaded_bytes) > 12:
                        # Check for common video file signatures (magic bytes)
                        # MP4: starts with 0x00 0x00 0x00 [size] 0x66 0x74 0x79 0x70 (ftyp)
                        # Or contains "ftyp" near the beginning
                        header = downloaded_bytes[:12]
                        if b'ftyp' not in downloaded_bytes[:100] and b'<!DOCTYPE' in downloaded_bytes[:100]:
                            # It's HTML!
                            os.remove(output_path)
                            raise ValueError("Downloaded file appears to be HTML, not a video file")
                        if b'<html' in downloaded_bytes[:100].lower():
                            # It's HTML!
                            os.remove(output_path)
                            raise ValueError("Downloaded file appears to be HTML, not a video file")

            print(f"   Downloaded {len(downloaded_bytes)} bytes")
            print(f"Video downloaded to {output_path}")
            return output_path
        except Exception as e:
            print(f"Error downloading video: {e}")
            raise

    @staticmethod
    async def stitch_videos(
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
            clip1 = VideoFileClip(original_video)
            clip2 = VideoFileClip(generated_video)

            # Validate clips loaded successfully
            if clip1 is None or clip2 is None:
                raise ValueError("Failed to load one or both video clips")

            print(f"   Original: {clip1.size} @ {clip1.fps}fps, duration: {clip1.duration:.2f}s")
            print(f"   Generated: {clip2.size} @ {clip2.fps}fps, duration: {clip2.duration:.2f}s")

            # Resize if needed (preserves aspect ratio by resizing)
            if clip1.size != clip2.size:
                print(f"   Resizing generated video from {clip2.size} to {clip1.size}")
                clip2 = vfx.Resize(new_size=clip1.size).apply(clip2)

            # NOTE: We do NOT adjust FPS here to avoid A/V desync issues
            # The concatenate_videoclips with method="chain" will handle FPS differences
            # by re-encoding both clips to a common FPS automatically
            if clip1.fps != clip2.fps:
                print(f"   WARNING: FPS mismatch ({clip1.fps} vs {clip2.fps}), concatenation will re-encode to match")

            # Use "chain" method instead of "compose" for more reliable concatenation
            # "chain" is simpler and less prone to creating black frames or corrupted transitions
            print(f"   Concatenating clips...")
            final_clip = concatenate_videoclips([clip1, clip2], method="chain")

            print(f"   Writing final video...")
            final_clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac'
            )
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
        motion_bucket_id: int = 127,
        duration: int = 8,
        manual_prompt: Optional[str] = None
    ) -> str:
        """
        Main workflow: Extract frames, analyze with AI, generate extension, stitch together

        Args:
            input_video: Path to original video
            output_path: Path for final output
            motion_bucket_id: Controls amount of motion for Replicate (1-255, higher = more motion)
            duration: Duration in seconds for Sora (4, 8, or 12)
            manual_prompt: Optional manual prompt override (skips AI analysis)

        Returns:
            Path to final stitched video
        """
        print(f"\n{'='*60}")
        print(f"Starting SMART video extension workflow")
        print(f"Using model: {self.model}")
        print(f"{'='*60}\n")

        # Validate input video duration
        print("Validating input video duration...")
        video = VideoFileClip(input_video)
        video_duration = video.duration
        video.close()

        if video_duration > 61:
            raise ValueError(f"Input video is too long: {video_duration:.2f}s (maximum: 60s)")
        if video_duration < 7:
            raise ValueError(f"Input video is too short: {video_duration:.2f}s (minimum: 6s)")

        print(f"✓ Video duration validated: {video_duration:.2f}s")

        # Temporary file paths
        analysis_frame_paths = []
        generation_frame_path = "temp_last_frame_smart.png"
        generated_video_path = "temp_generated_video_smart.mp4"
        try:
            # Step 1: Generate continuation prompt + select best frame (manual, Gemini video, or frame-based)
            selected_timestamp = None  # Will be set by Gemini analysis

            if manual_prompt:
                print(f"Using manual prompt: \"{manual_prompt}\"")
                prompt = manual_prompt
            else:
                # Try Gemini video+audio analysis first (if veo_client available)
                if hasattr(self, 'veo_client'):
                    try:
                        print("Attempting Gemini video+audio analysis...")
                        result = await self.analyze_video_with_gemini(
                            input_video,
                            duration_to_analyze=5
                        )
                        prompt = result["prompt"]
                        relative_timestamp = result.get("timestamp_sec", 2.5)  # Default to middle

                        # Validate timestamp range
                        if not (0 <= relative_timestamp <= 5):
                            print(f"⚠ Invalid timestamp {relative_timestamp:.2f}s, using 2.5s")
                            relative_timestamp = 2.5

                        # Calculate actual timestamp in video: (video_duration - 5) + relative_timestamp
                        selected_timestamp = (video_duration - 5) + relative_timestamp
                        print(f"✓ Selected frame at {selected_timestamp:.2f}s in original video")

                    except Exception as e:
                        print(f"⚠ Gemini analysis failed: {e}")
                        print("→ Falling back to frame-based analysis...")

                        # Fallback: Extract frames and use GPT-4o Vision
                        analysis_frame_paths = await self.extract_multiple_frames(
                            input_video,
                            num_frames=5,
                            target_size=(512, 512)
                        )
                        prompt = await self.analyze_frames_with_vision(analysis_frame_paths)
                else:
                    # No Google client, use frame-based analysis
                    print("Using frame-based analysis (no Gemini client)...")
                    analysis_frame_paths = await self.extract_multiple_frames(
                        input_video,
                        num_frames=5,
                        target_size=(512, 512)
                    )
                    prompt = await self.analyze_frames_with_vision(analysis_frame_paths)

            # Step 2: Extract frame for video generation
            # Use 1024x576 for Replicate/SVD, 1280x720 for Sora
            target_size = (1024, 576) if self.model == "replicate" else (1280, 720)

            if selected_timestamp is not None:
                # Use Gemini-selected timestamp
                await self.extract_frame_at_timestamp(
                    input_video,
                    timestamp_sec=selected_timestamp,
                    output_path=generation_frame_path,
                    target_size=target_size
                )
            else:
                # Fallback to last frame
                await self.extract_last_frame(input_video, generation_frame_path, target_size=target_size)

            # Step 4: Generate video from frame using AI prompt
            video_result, is_local_file = await self.generate_video_from_image(
                generation_frame_path,
                prompt=prompt,
                motion_bucket_id=motion_bucket_id,
                duration=duration
            )

            # Step 5: Download generated video (if it's a URL) or use local file
            if is_local_file:
                # Veo returns a local file path
                generated_video_path = video_result
            else:
                # Other models return URLs
                headers = None
                if self.model == "sora":
                    # Sora requires auth headers for the content endpoint
                    headers = self.openai_headers
                await self.download_video(video_result, generated_video_path, headers=headers)

            # Step 6: Stitch videos together
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
            # Cleanup temporary files (but keep generation frame for inspection)
            temp_files = analysis_frame_paths + [generated_video_path]
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        print(f"Cleaned up {temp_file}")
                    except Exception as e:
                        print(f"Could not remove {temp_file}: {e}")

            # Keep the generation frame for inspection
            if os.path.exists(generation_frame_path):
                print(f"Kept {generation_frame_path} for inspection")


async def main():
    """Command-line interface for smart video extension"""
    parser = argparse.ArgumentParser(
        description="Extend a video using AI-analyzed prompts with Replicate or Sora",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using Replicate (default, cheaper, faster, no audio)
  python extend_video_smart.py my_video.mp4
  python extend_video_smart.py input.mp4 --output result.mp4 --motion 180

  # Using Runway (no audio, good quality, moderate cost)
  python extend_video_smart.py my_video.mp4 --model runway --duration 10
  python extend_video_smart.py input.mp4 --model runway --manual-prompt "person continues walking"

  # Using Google Veo 3.1 (with audio!, high quality, less moderation than Sora)
  python extend_video_smart.py my_video.mp4 --model veo --duration 8
  python extend_video_smart.py input.mp4 --model veo --manual-prompt "camera continues panning"

  # Using Sora (with audio, highest quality, most expensive, strict moderation)
  python extend_video_smart.py my_video.mp4 --model sora --duration 8
  python extend_video_smart.py input.mp4 --model sora --manual-prompt "camera pans left slowly"
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
        '--model',
        type=str,
        default='replicate',
        choices=['replicate', 'sora', 'runway', 'veo'],
        help='Video generation model to use (default: replicate)'
    )
    parser.add_argument(
        '--motion', '-m',
        type=int,
        default=127,
        help='Motion intensity for Replicate (1-255, default: 127). Higher = more motion'
    )
    parser.add_argument(
        '--duration', '-d',
        type=int,
        default=8,
        choices=[4, 5, 8, 10, 12],
        help='Video duration in seconds. Sora: 4, 8, or 12. Runway: up to 10 (default: 8)'
    )
    parser.add_argument(
        '--manual-prompt',
        type=str,
        default=None,
        help='Optional: Provide manual prompt instead of AI analysis'
    )
    parser.add_argument(
        '--openai-api-key',
        type=str,
        default=None,
        help='OpenAI API key (defaults to MY_OWN_OPENAI_API_KEY env var)'
    )
    parser.add_argument(
        '--replicate-api-key',
        type=str,
        default=None,
        help='Replicate API key (defaults to REPLICATE_API_TOKEN env var, only needed for --model replicate)'
    )
    parser.add_argument(
        '--runway-api-key',
        type=str,
        default=None,
        help='Runway API key (defaults to RUNWAYML_API_SECRET env var, only needed for --model runway)'
    )
    parser.add_argument(
        '--google-api-key',
        type=str,
        default=None,
        help='Google API key (defaults to GOOGLE_API_KEY env var, only needed for --model veo)'
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
        extender = SmartVideoExtender(
            openai_api_key=args.openai_api_key,
            replicate_api_key=args.replicate_api_key,
            runway_api_key=args.runway_api_key,
            google_api_key=args.google_api_key,
            model=args.model
        )
        result = await extender.extend_video(
            input_video=args.input_video,
            output_path=args.output,
            motion_bucket_id=args.motion,
            duration=args.duration,
            manual_prompt=args.manual_prompt
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

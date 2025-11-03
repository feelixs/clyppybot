#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sora Video Extension Script

Takes an input video, extracts the last frame, sends it to OpenAI's Sora API
to generate a continuation, then stitches the original and generated videos together.

Usage:
    python extend_video.py input_video.mp4 [--output extended_video.mp4] [--prompt "custom prompt"]
"""

import asyncio
import os
import sys
import argparse
from test.sora import SoraVideoExtender
from test.env import DEFAULT_PROMPT

async def main():
    """Command-line interface for video extension"""
    parser = argparse.ArgumentParser(
        description="Extend a video using OpenAI's Sora API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python extend_video.py my_video.mp4
  python extend_video.py input.mp4 --output result.mp4
  python extend_video.py clip.mp4 --prompt "Add dramatic slow motion ending"
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
        help='Custom prompt for video generation'
    )

    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='OpenAI API key (defaults to OPENAI_API_KEY env var)'
    )

    args = parser.parse_args()

    # Validate input file exists
    if not os.path.exists(args.input_video):
        print(f"Error: Input video not found: {args.input_video}")
        sys.exit(1)

    try:
        # Initialize extender
        extender = SoraVideoExtender(api_key=args.api_key)

        # Run extension workflow
        result = await extender.extend_video(
            input_video=args.input_video,
            output_path=args.output,
            prompt=args.prompt
        )

        print(f"\n( All done! Your extended video is ready at: {result}")

    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

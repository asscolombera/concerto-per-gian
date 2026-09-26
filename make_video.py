#!/usr/bin/env python3
"""
Ken Burns Dynamic Slideshow CLI Tool
Automates creation of an MP4 slideshow with smooth pan/zoom effects.
Guarantees 100% straight/unidirectional movement and adds fade in/out from/to black.
"""

import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
EXCLUDE_KEYWORDS = {"small", "thumb"}


def discover_images(input_dir: str) -> list[Path]:
    """
    Recursively finds all supported images in input_dir, excluding files
    containing 'small' or 'thumb' in their name (case-insensitive).
    """
    input_path = Path(input_dir).resolve()
    valid_paths = []

    for path in input_path.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            filename_lower = path.name.lower()
            if not any(keyword in filename_lower for keyword in EXCLUDE_KEYWORDS):
                valid_paths.append(path)

    return sorted(valid_paths)


def check_ffmpeg() -> None:
    """Ensures FFmpeg is available on the system PATH."""
    if shutil.which("ffmpeg") is None:
        print("Error: 'ffmpeg' binary not found in system PATH. Please install FFmpeg.", file=sys.stderr)
        sys.exit(1)


def parse_resolution(res_str: str) -> tuple[int, int]:
    """Parses WxH resolution string into width and height integers."""
    try:
        w, h = map(int, res_str.lower().split("x"))
        return w, h
    except ValueError:
        print(f"Error: Invalid resolution format '{res_str}'. Expected WxH (e.g. 1920x1080).", file=sys.stderr)
        sys.exit(1)


def generate_zoompan_expr(total_frames: int, resolution: str, fps: int, speed_multiplier: float) -> str:
    """
    Generates a zoompan filter string with a fixed anchor target to guarantee
    strictly straight, 1-way zoom-in motion without mid-slide direction changes.
    """
    # Randomize zoom depth per image (8% to 35% zoom, scaled by speed_multiplier)
    base_zoom_delta = random.uniform(0.08, 0.35) * speed_multiplier
    base_zoom_delta = min(max(base_zoom_delta, 0.04), 0.60)  # Safe bounds

    z_expr = f"1.0+{base_zoom_delta:.4f}*(on/{total_frames})"

    # Select a FIXED anchor point (ax, ay) in normalized [0.0, 1.0] coordinates
    anchor_presets = [
        (0.5, 0.5),   # Center
        (0.1, 0.1),   # Top-Left
        (0.9, 0.1),   # Top-Right
        (0.1, 0.9),   # Bottom-Left
        (0.9, 0.9),   # Bottom-Right
        (0.5, 0.1),   # Top-Center
        (0.5, 0.9),   # Bottom-Center
        (0.1, 0.5),   # Left-Center
        (0.9, 0.5),   # Right-Center
    ]

    # 70% chance of a preset anchor, 30% chance of a completely random focal point
    if random.random() < 0.7:
        ax, ay = random.choice(anchor_presets)
    else:
        ax = round(random.uniform(0.15, 0.85), 2)
        ay = round(random.uniform(0.15, 0.85), 2)

    # Fixed anchor math guarantees 100% linear, 1-way motion toward (ax, ay)
    x_expr = f"{ax:.2f}*(iw-iw/zoom)"
    y_expr = f"{ay:.2f}*(ih-ih/zoom)"

    return f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={total_frames}:s={resolution}:fps={fps}"


def generate_slideshow(
    input_dir: str,
    output_file: str,
    duration: float = 4.0,
    fade_duration: float = 0.5,
    fps: int = 30,
    resolution: str = "1920x1080",
    pan_speed: float = 1.0,
    crf: int = 20,
    auto_confirm: bool = False,
    verbose: bool = False,
) -> None:
    check_ffmpeg()

    input_path = Path(input_dir).resolve()
    if not input_path.is_dir():
        print(f"Error: Input directory '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    image_paths = discover_images(str(input_path))
    if not image_paths:
        print(
            f"Error: No valid image files found in '{input_path}' after filtering out 'small'/'thumb' files.",
            file=sys.stderr,
        )
        sys.exit(1)

    out_w, out_h = parse_resolution(resolution)

    # High-resolution canvas size matching target aspect ratio
    canvas_w = 8000
    canvas_h = int(canvas_w * (out_h / out_w))
    if canvas_h % 2 != 0:
        canvas_h += 1

    # Clamp fade duration so it doesn't exceed half the slide length
    actual_fade = min(fade_duration, duration / 2.0)
    fade_out_start = max(0.0, duration - actual_fade)

    total_images = len(image_paths)
    total_duration_sec = total_images * duration
    minutes, seconds = divmod(total_duration_sec, 60)

    print("\n" + "=" * 55)
    print(" 🎬 SLIDESHOW GENERATION PREVIEW")
    print("=" * 55)
    print(f" • Input Directory        : {input_path}")
    print(f" • Valid Images Found    : {total_images} (recursively scanned, 'small'/'thumb' ignored)")
    print(f" • Duration Per Slide    : {duration} seconds")
    print(f" • Fade Duration         : {actual_fade}s in / {actual_fade}s out")
    print(f" • Expected Total Length : {int(minutes)}m {seconds:.1f}s ({total_duration_sec:.1f} seconds total)")
    print(f" • Output Resolution     : {resolution} @ {fps} fps")
    print(f" • Pan/Zoom Speed Scale  : {pan_speed}x")
    print(f" • Target Output File    : {Path(output_file).resolve()}")
    print("=" * 55 + "\n")

    if not auto_confirm:
        choice = input("Do you want to proceed with generating the video? [y/N]: ").strip().lower()
        if choice not in ("y", "yes"):
            print("Operation canceled. Exiting without rendering.")
            sys.exit(0)

    print("\nStarting video processing pipeline...")

    total_frames = int(duration * fps)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_clips = []

        for idx, img_path in enumerate(image_paths, start=1):
            temp_clip_path = os.path.join(temp_dir, f"clip_{idx:04d}.mp4")
            temp_clips.append(temp_clip_path)

            zoompan_filter = generate_zoompan_expr(
                total_frames=total_frames,
                resolution=resolution,
                fps=fps,
                speed_multiplier=pan_speed,
            )

            # Build filter chain: aspect ratio scale -> pad -> zoompan -> fade in & fade out
            filters = [
                f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=decrease",
                f"pad={canvas_w}:{canvas_h}:(ow-iw)/2:(oh-ih)/2:color=black",
                zoompan_filter,
            ]

            if actual_fade > 0:
                filters.append(f"fade=t=in:st=0:d={actual_fade:.2f}")
                filters.append(f"fade=t=out:st={fade_out_start:.2f}:d={actual_fade:.2f}")

            filter_chain = ",".join(filters)

            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(img_path),
                "-vf", filter_chain,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", str(crf),
                temp_clip_path,
            ]

            print(f"[{idx}/{total_images}] Rendering clip for: {img_path.name}")

            stdout_dest = None if verbose else subprocess.DEVNULL
            stderr_dest = None if verbose else subprocess.DEVNULL

            result = subprocess.run(cmd, stdout=stdout_dest, stderr=stderr_dest)
            if result.returncode != 0:
                print(f"Error: FFmpeg processing failed on file '{img_path}'.", file=sys.stderr)
                sys.exit(result.returncode)

        # Concatenate intermediate clips
        concat_list_file = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for clip in temp_clips:
                safe_clip_path = clip.replace("'", "'\\''")
                f.write(f"file '{safe_clip_path}'\n")

        print("\nConcatenating clips into final slideshow movie...")
        concat_cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_file,
            "-c", "copy",
            output_file,
        ]

        result = subprocess.run(concat_cmd, stdout=stdout_dest, stderr=stderr_dest)
        if result.returncode != 0:
            print("Error: FFmpeg failed during final concatenation.", file=sys.stderr)
            sys.exit(result.returncode)

    print(f"\nSuccess! Output slideshow saved to: {Path(output_file).resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Ken Burns slideshow from a directory of images."
    )
    parser.add_argument(
        "-i", "--input-dir",
        default="./my_images",
        help="Path to root folder containing source images (default: ./my_images)",
    )
    parser.add_argument(
        "-o", "--output",
        default="slideshow.mp4",
        help="Destination path for generated MP4 (default: slideshow.mp4)",
    )
    parser.add_argument(
        "-d", "--duration",
        type=float,
        default=4.0,
        help="Slide duration in seconds per image (default: 4.0)",
    )
    parser.add_argument(
        "-f", "--fade-duration",
        type=float,
        default=0.5,
        help="Fade in/out duration in seconds per slide (default: 0.5, set to 0 to disable)",
    )
    parser.add_argument(
        "-m", "--pan-speed",
        type=float,
        default=1.0,
        help="Movement speed multiplier (default: 1.0, e.g. 1.5 = deeper zoom, 0.5 = subtle)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Frame rate of generated video (default: 30)",
    )
    parser.add_argument(
        "-s", "--size",
        default="1920x1080",
        help="Output resolution WxH (default: 1920x1080)",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="H.264 quality CRF factor (lower = higher quality, default: 20)",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Automatically confirm and bypass the prompt before rendering",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show raw FFmpeg encoder output streams",
    )

    args = parser.parse_args()

    generate_slideshow(
        input_dir=args.input_dir,
        output_file=args.output,
        duration=args.duration,
        fade_duration=args.fade_duration,
        fps=args.fps,
        resolution=args.size,
        pan_speed=args.pan_speed,
        crf=args.crf,
        auto_confirm=args.yes,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()

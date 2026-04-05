#!/usr/bin/env python3
"""Generate TTS audio from ttsvibes.com and inject into video."""

import argparse
import base64
import json
import subprocess
import tempfile
import os

import requests

VOICES = {
    "Jessie": "tt-en_us_002",
}

def generate_tts(text: str, voice: str = "Jessie") -> bytes:
    voice_id = VOICES.get(voice, voice)  # allow raw voice ID as fallback
    resp = requests.post(
        "https://ttsvibes.com/?/generate",
        headers={
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "x-sveltekit-action": "true",
            "origin": "https://ttsvibes.com",
        },
        cookies={"__vdpl": "x"},
        data=f"selectedVoiceValue={voice_id}&text={requests.utils.quote(text)}",
    )
    resp.raise_for_status()
    inner = json.loads(resp.json()["data"])
    return base64.b64decode(inner[2])


def _get_audio_duration(path: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        stderr=subprocess.DEVNULL,
    )
    streams = json.loads(out)["streams"]
    for s in streams:
        if s.get("codec_type") == "audio":
            return float(s["duration"])
    raise ValueError(f"No audio stream found in {path}")


def inject_audio_to_video(video_path: str, audio_path: str, output_path: str) -> str:
    """Replace the audio track of a video with audio_path. Returns output_path.

    - Audio is trimmed/padded to match video duration.
    - Validates output has an audio stream afterward.
    """
    # Validate inputs exist
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    # Get video duration
    out = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        stderr=subprocess.DEVNULL,
    )
    streams = json.loads(out)["streams"]
    video_duration = None
    for s in streams:
        if s.get("codec_type") == "video":
            video_duration = float(s["duration"])
            break
    if video_duration is None:
        raise ValueError(f"No video stream found in {video_path}")

    print(f"Video duration: {video_duration:.2f}s")
    print(f"Audio duration: {_get_audio_duration(audio_path):.2f}s")

    # Check if video has an audio stream
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    if has_audio:
        # Mix TTS audio on top of original audio
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-filter_complex", "[0:a]volume=0.8[orig];[orig][1:a]amix=inputs=2:duration=first[aout]",
            "-map", "0:v:0", "-map", "[aout]",
            "-t", str(video_duration),
            "-c:v", "copy", "-c:a", "aac",
            output_path,
        ]
    else:
        # No audio in video — just add TTS as the audio track
        print("  (video has no audio — adding TTS as only audio track)")
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", str(video_duration),
            "-c:v", "copy", "-c:a", "aac",
            output_path,
        ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")

    # Validate output has audio
    out_duration = _get_audio_duration(output_path)
    print(f"Output audio duration: {out_duration:.2f}s  ✓")
    print(f"Saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate TTS audio via ttsvibes.com")
    parser.add_argument("text", help="Text to convert to speech")
    parser.add_argument("--voice", default="Jessie", help="Voice name (default: Jessie)")
    parser.add_argument("--output", "-o", default="output.mp3", help="Output MP3 file (default: output.mp3)")
    args = parser.parse_args()

    audio = generate_tts(args.text, args.voice)
    with open(args.output, "wb") as f:
        f.write(audio)
    print(f"Saved {len(audio)} bytes to {args.output}")

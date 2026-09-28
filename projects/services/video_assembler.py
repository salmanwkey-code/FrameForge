"""
projects/services/video_assembler.py
--------------------------------------
Final video assembly pipeline using FFmpeg.

Image-Based Pipeline:
  1. Gather all GeneratedImage instances ordered by chapter and scene
  2. Compute per-scene duration synced with Chapter Voiceovers (or timestamps / default)
  3. Render each scene with documentary-style Ken Burns motion (zooms / pans)
  4. Concatenate scene clips into a master visual track matching project resolution & aspect ratio
  5. Concatenate chapter voiceovers into a unified audio stream
  6. Mux master video + audio track into high-quality final MP4 in project exports directory

Requirements:
  - ffmpeg installed on PATH
  - ffmpeg-python or subprocess access to ffmpeg
"""

import os
import json
import logging
import subprocess
import tempfile
import time
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)

try:
    import ffmpeg
    FFMPEG_AVAILABLE = True
except ImportError:
    FFMPEG_AVAILABLE = False
    logger.warning("ffmpeg-python not installed. Video assembly will use subprocess.")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AssemblyError(Exception):
    """Raised when final video assembly fails."""


class AssemblyUnavailable(Exception):
    """Raised when ffmpeg is not available on the system."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_ffmpeg():
    """Verify that ffmpeg binary is installed and operational."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, timeout=10
        )
        if result.returncode != 0:
            raise AssemblyUnavailable("ffmpeg binary returned non-zero exit code.")
    except FileNotFoundError:
        raise AssemblyUnavailable(
            "ffmpeg is not installed or not on PATH. "
            "Install it via: winget install ffmpeg"
        )


def _get_media_root() -> str:
    try:
        from django.conf import settings
        return settings.MEDIA_ROOT
    except Exception:
        return os.path.join(os.path.dirname(__file__), "..", "..", "media")


def _get_resolution(aspect_ratio: str, video_quality: str) -> Tuple[int, int]:
    """
    Map aspect ratio and quality choice to (width, height) pixels.
    """
    matrix = {
        "16:9": {
            "720p": (1280, 720),
            "1080p": (1920, 1080),
            "4K": (3840, 2160),
        },
        "9:16": {
            "720p": (720, 1280),
            "1080p": (1080, 1920),
            "4K": (2160, 3840),
        },
        "1:1": {
            "720p": (720, 720),
            "1080p": (1080, 1080),
            "4K": (2160, 2160),
        },
    }
    ratio_clean = (aspect_ratio or "16:9").strip()
    quality_clean = (video_quality or "1080p").strip()
    
    if ratio_clean in matrix and quality_clean in matrix[ratio_clean]:
        return matrix[ratio_clean][quality_clean]
    elif ratio_clean in matrix:
        return matrix[ratio_clean].get("1080p", (1920, 1080))
    return (1920, 1080)


def _parse_time_seconds(time_str: Optional[str]) -> Optional[float]:
    """Parse string timestamp like '00:15', '1:05.5', '65' into seconds."""
    if not time_str:
        return None
    time_str = str(time_str).strip()
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        return float(time_str)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Image-Based Final Video Assembly Pipeline
# ---------------------------------------------------------------------------

def assemble_from_images(project, output_filename: str = None) -> str:
    """
    Assemble all GeneratedImage files and Chapter Voiceovers into a polished MP4.
    
    Features:
      - Ken Burns camera motion per scene (varied zooms and pans)
      - Visual settings integration (aspect ratio & resolution)
      - Voiceover synchronization per chapter
      - Pure image workflow (no external video generator required)

    Returns:
      Absolute path to the rendered MP4 file.
    """
    _check_ffmpeg()

    from django.utils.text import slugify
    from projects.models import Chapter, GeneratedImage, ImagePrompt, ProjectVisualSettings

    media_root = _get_media_root()
    chapters = Chapter.objects.filter(project=project).order_by("chapter_no")
    if not chapters.exists():
        raise AssemblyError("No chapters found for this project.")

    visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=project)
    target_w, target_h = _get_resolution(visual_settings.aspect_ratio, visual_settings.video_quality)
    logger.info("Rendering project %s at %dx%d (%s, %s)", project.id, target_w, target_h, visual_settings.aspect_ratio, visual_settings.video_quality)

    # -----------------------------------------------------------------------
    # 1. Collect all scenes & audio files in sequence
    # -----------------------------------------------------------------------
    scene_items: List[Dict] = []
    vo_files: List[str] = []
    total_scene_idx = 0

    for chapter in chapters:
        prompts = ImagePrompt.objects.filter(chapter=chapter).order_by("prompt_number")
        if not prompts.exists():
            continue

        # Check for chapter voiceover
        vo_path = None
        vo_duration = None
        try:
            vo = chapter.voiceover
            if vo.status == "completed" and vo.audio_file and vo.audio_file.name:
                candidate_path = os.path.join(media_root, vo.audio_file.name)
                if os.path.exists(candidate_path):
                    vo_path = candidate_path
                    vo_duration = float(vo.duration_seconds) if vo.duration_seconds > 0 else None
        except Exception:
            pass

        if vo_path:
            vo_files.append(vo_path)

        # Calculate duration per scene in this chapter
        num_prompts = prompts.count()
        if vo_duration and vo_duration > 0 and num_prompts > 0:
            duration_per_prompt = max(2.5, vo_duration / num_prompts)
        else:
            duration_per_prompt = 5.0

        for prompt in prompts:
            # Find the generated image for this prompt
            gi = prompt.generated_images.order_by("-created_at").first()
            if not gi or not gi.image_file or not gi.image_file.name:
                raise AssemblyError(
                    f"Missing generated image for Chapter {chapter.chapter_no}, Scene {prompt.prompt_number} "
                    f"({prompt.prompt_text[:40]}...). Please generate all scene images first."
                )

            img_path = os.path.join(media_root, gi.image_file.name)
            if not os.path.exists(img_path):
                raise AssemblyError(
                    f"Image file not found on disk: {img_path} (Chapter {chapter.chapter_no}, Scene {prompt.prompt_number})."
                )

            # Determine scene duration
            scene_duration = duration_per_prompt
            if not vo_duration:
                start_sec = _parse_time_seconds(prompt.start_time)
                end_sec = _parse_time_seconds(prompt.end_time)
                if start_sec is not None and end_sec is not None and end_sec > start_sec:
                    scene_duration = max(2.0, end_sec - start_sec)

            scene_items.append({
                "chapter_no": chapter.chapter_no,
                "prompt_number": prompt.prompt_number,
                "image_path": img_path,
                "duration": round(scene_duration, 2),
                "scene_idx": total_scene_idx,
            })
            total_scene_idx += 1

    if not scene_items:
        raise AssemblyError("No scenes or images found to render. Please generate scene images first.")

    # -----------------------------------------------------------------------
    # 2. Prepare export output directory
    # -----------------------------------------------------------------------
    title_slug = slugify(project.title) or "untitled-project"
    export_dir = os.path.join(
        media_root,
        "users",
        str(project.user_id),
        "projects",
        title_slug[:50].rstrip("-"),
        "exports",
    )
    os.makedirs(export_dir, exist_ok=True)

    if not output_filename:
        timestamp = int(time.time())
        output_filename = f"final_{timestamp}.mp4"

    output_path = os.path.join(export_dir, output_filename)

    # -----------------------------------------------------------------------
    # 3. Render Ken Burns clips for each scene
    # -----------------------------------------------------------------------
    temp_clips = []
    temp_dir = tempfile.mkdtemp(prefix="yts_render_")

    try:
        logger.info("Rendering %d scene clips with documentary Ken Burns motion...", len(scene_items))

        scale_filter = (
            f"scale='max({target_w}*1.5,iw*1.5)':'max({target_h}*1.5,ih*1.5)':force_original_aspect_ratio=increase,"
            f"crop='max({target_w}*1.5,iw)':'max({target_h}*1.5,ih)'"
        )

        for item in scene_items:
            idx = item["scene_idx"]
            duration = item["duration"]
            img_path = item["image_path"]
            frames = max(25, int(duration * 25))
            clip_path = os.path.join(temp_dir, f"scene_{idx:03d}.mp4")

            # 4 cinematic variations:
            # 0: Slow Zoom In to center
            # 1: Slow Zoom Out from center
            # 2: Gentle Pan Left across wide framing
            # 3: Gentle Pan Right across wide framing
            variation = idx % 4
            if variation == 0:
                vf = (
                    f"{scale_filter},"
                    f"zoompan=z='min(zoom+0.0015,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={frames}:s={target_w}x{target_h}:fps=25,format=yuv420p"
                )
            elif variation == 1:
                vf = (
                    f"{scale_filter},"
                    f"zoompan=z='if(lte(zoom,1.0),1.15,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={frames}:s={target_w}x{target_h}:fps=25,format=yuv420p"
                )
            elif variation == 2:
                vf = (
                    f"{scale_filter},"
                    f"zoompan=z='1.1':x='if(lte(on,1),(iw-iw/zoom),max(0,x-((iw-iw/zoom)/{frames})))':y='ih/2-(ih/zoom/2)':"
                    f"d={frames}:s={target_w}x{target_h}:fps=25,format=yuv420p"
                )
            else:
                vf = (
                    f"{scale_filter},"
                    f"zoompan=z='1.1':x='if(lte(on,1),0,min(iw-iw/zoom,x+((iw-iw/zoom)/{frames})))':y='ih/2-(ih/zoom/2)':"
                    f"d={frames}:s={target_w}x{target_h}:fps=25,format=yuv420p"
                )

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", img_path,
                "-vf", vf,
                "-t", str(duration),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "stillimage",
                "-pix_fmt", "yuv420p",
                clip_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                err = res.stderr[-500:] if res.stderr else "Unknown ffmpeg error"
                raise AssemblyError(f"Failed rendering scene {idx + 1} (Chapter {item['chapter_no']}): {err}")

            temp_clips.append(clip_path)

        # -------------------------------------------------------------------
        # 4. Concatenate all scene clips
        # -------------------------------------------------------------------
        concat_list_path = os.path.join(temp_dir, "concat_clips.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for clip in temp_clips:
                safe_clip = clip.replace("\\", "/")
                f.write(f"file '{safe_clip}'\n")

        concat_video_path = os.path.join(temp_dir, "_concat_video.mp4")
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            concat_video_path
        ]
        res = subprocess.run(concat_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            err = res.stderr[-500:] if res.stderr else "Unknown concat error"
            raise AssemblyError(f"Failed concatenating scene clips: {err}")

        # -------------------------------------------------------------------
        # 5. Concatenate voiceovers & mux with visual track
        # -------------------------------------------------------------------
        if vo_files:
            vo_list_path = os.path.join(temp_dir, "concat_vo.txt")
            with open(vo_list_path, "w", encoding="utf-8") as f:
                for vo in vo_files:
                    safe_vo = vo.replace("\\", "/")
                    f.write(f"file '{safe_vo}'\n")

            concat_audio_path = os.path.join(temp_dir, "_concat_audio.mp3")
            vo_cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", vo_list_path,
                "-c:a", "libmp3lame",
                "-q:a", "2",
                concat_audio_path
            ]
            res = subprocess.run(vo_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                err = res.stderr[-500:] if res.stderr else "Unknown audio concat error"
                raise AssemblyError(f"Failed concatenating voiceovers: {err}")

            # Merge video + audio
            mux_cmd = [
                "ffmpeg", "-y",
                "-i", concat_video_path,
                "-i", concat_audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                output_path
            ]
            res = subprocess.run(mux_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                err = res.stderr[-500:] if res.stderr else "Unknown mux error"
                raise AssemblyError(f"Failed muxing video and audio: {err}")
        else:
            # Re-wrap visual track cleanly without audio
            mux_cmd = [
                "ffmpeg", "-y",
                "-i", concat_video_path,
                "-c:v", "copy",
                output_path
            ]
            res = subprocess.run(mux_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                err = res.stderr[-500:] if res.stderr else "Unknown re-encode error"
                raise AssemblyError(f"Failed rendering final video: {err}")

    finally:
        # Clean up temporary clips and lists
        try:
            for root, dirs, files in os.walk(temp_dir, topdown=False):
                for f in files:
                    os.unlink(os.path.join(root, f))
                for d in dirs:
                    os.rmdir(os.path.join(root, d))
            os.rmdir(temp_dir)
        except Exception as cleanup_err:
            logger.warning("Error cleaning temporary render directory %s: %s", temp_dir, cleanup_err)

    if not os.path.exists(output_path):
        raise AssemblyError("Video assembly completed but the final output file was not found.")

    logger.info("Final video assembly succeeded: %s (%d bytes)", output_path, os.path.getsize(output_path))
    return output_path


# ---------------------------------------------------------------------------
# Preserved Legacy Video-Clip Pipeline (Isolated for potential future use)
# ---------------------------------------------------------------------------

def _assemble_from_animated_clips(project, output_filename: str = None) -> str:
    """
    [DEPRECATED / PRESERVED] Assemble animated video clips + voiceovers into final MP4.
    Kept safely isolated in case external video animation providers are re-enabled.
    """
    _check_ffmpeg()

    from django.utils.text import slugify
    from projects.models import AnimatedVideo, Voiceover, Chapter

    chapters = Chapter.objects.filter(project=project).order_by("chapter_no")
    media_root = _get_media_root()

    video_clips = []
    vo_files = []

    for chapter in chapters:
        avs = AnimatedVideo.objects.filter(
            chapter=chapter,
            status="generated"
        ).order_by("image_prompt__prompt_number")

        for av in avs:
            if av.video_file and av.video_file.name:
                clip_path = os.path.join(media_root, av.video_file.name)
                if os.path.exists(clip_path):
                    video_clips.append(clip_path)

        try:
            vo = chapter.voiceover
            if vo.status == "completed" and vo.audio_file:
                vo_path = os.path.join(media_root, vo.audio_file.name)
                if os.path.exists(vo_path):
                    vo_files.append(vo_path)
        except Exception:
            pass

    if not video_clips:
        raise AssemblyError("No animated video clips found for this project.")

    title_slug = slugify(project.title) or "untitled-project"
    export_dir = os.path.join(
        media_root,
        "users",
        str(project.user_id),
        "projects",
        title_slug[:50].rstrip("-"),
        "exports",
    )
    os.makedirs(export_dir, exist_ok=True)

    if not output_filename:
        timestamp = int(time.time())
        output_filename = f"final_{timestamp}.mp4"

    output_path = os.path.join(export_dir, output_filename)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as concat_file:
        for clip in video_clips:
            concat_file.write(f"file '{clip}'\n")
        concat_list_path = concat_file.name

    try:
        concat_video_path = os.path.join(export_dir, "_concat_video.mp4")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", concat_video_path], check=True)

        if vo_files:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as vo_file:
                for vo in vo_files:
                    vo_file.write(f"file '{vo}'\n")
                vo_list_path = vo_file.name

            concat_audio_path = os.path.join(export_dir, "_concat_audio.mp3")
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", vo_list_path, "-c", "copy", concat_audio_path], check=True)
            os.unlink(vo_list_path)

            subprocess.run([
                "ffmpeg", "-y", "-i", concat_video_path, "-i", concat_audio_path,
                "-vcodec", "libx264", "-acodec", "aac", "-audio_bitrate", "192k",
                "-shortest", output_path
            ], check=True)
            os.unlink(concat_audio_path)
        else:
            subprocess.run(["ffmpeg", "-y", "-i", concat_video_path, "-vcodec", "libx264", "-acodec", "aac", output_path], check=True)

        if os.path.exists(concat_video_path):
            os.unlink(concat_video_path)
    finally:
        if os.path.exists(concat_list_path):
            os.unlink(concat_list_path)

    return output_path


# Alias for backward compatibility
def assemble_final_video(project, output_filename: str = None) -> str:
    """Primary entry point: assembles final video directly from generated images."""
    return assemble_from_images(project, output_filename)

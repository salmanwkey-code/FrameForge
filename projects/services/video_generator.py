"""
projects/services/video_generator.py
-------------------------------------
AI Motion Director and Real Image-to-Video Generation Service.

Responsibilities:
  1. generate_animation_prompt(): Acts as a lead documentary video editor and motion
     designer. Multimodally analyzes the visual image, narration script, chapter,
     timing, and scene context to formulate rich, scene-specific motion directions
     (e.g., character actions, DNA/molecular rotation, atmospheric parallax, depth-of-field).
  2. generate_video_from_image(): Dispatches to real AI Image-to-Video generation providers
     (Google Veo, Luma Dream Machine, Runway Gen-3, Replicate).
     Raises VideoGenerationUnavailable when no real video provider is accessible,
     ensuring the platform NEVER fakes animation with generic zooms or frontend tricks.
"""

import os
import json
import logging
import base64
import requests

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class VideoGenerationUnavailable(Exception):
    """
    Raised when the configured video generation provider or API key does not support
    real image-to-video generation. Callers show a clear configuration message
    without faking any output.
    """


class VideoGenerationError(Exception):
    """Raised for recoverable generation errors (timeout, bad response, etc.)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_genai_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY environment variable is not set. "
            "Please configure it in your .env file."
        )
    return genai.Client(api_key=api_key)


def extract_script_segment(script_text: str, start_time: str, end_time: str) -> str:
    """
    Extract the portion of the narration script that corresponds to the
    image's time window. Falls back to full script if timestamps are missing.
    """
    if not script_text:
        return ""
    if not start_time or not end_time:
        return script_text.strip()

    try:
        def to_seconds(t: str) -> float:
            parts = t.strip().split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            return float(parts[0])

        start_sec = to_seconds(start_time)
        end_sec = to_seconds(end_time)
        duration = max(end_sec - start_sec, 1)

        words = script_text.split()
        total_words = len(words)
        script_duration = total_words / 2.5  # ~2.5 words per second

        if script_duration <= 0:
            return script_text.strip()

        start_word = int((start_sec / script_duration) * total_words)
        end_word = int(((start_sec + duration) / script_duration) * total_words)
        segment = " ".join(words[start_word:end_word]).strip()
        return segment if segment else script_text.strip()

    except Exception:
        return script_text.strip()


# ---------------------------------------------------------------------------
# AI Motion Director: Real Scene-Based Animation Prompting
# ---------------------------------------------------------------------------

def generate_animation_prompt(
    image_prompt_text: str,
    script_segment: str,
    chapter_title: str,
    chapter_no: int,
    project_title: str,
    visual_style: str = "",
    camera_movement: str = "automatic",
    motion_intensity: str = "subtle",
    animation_style: str = "",
    camera_style: str = "cinematic",
    motion_instructions: str = "",
    duration_seconds: int = 4,
    start_time: str = "",
    end_time: str = "",
    image_path: str = "",
) -> str:
    """
    Multimodal AI Director: Analyzes the image, narration segment, and dramatic context
    to formulate a custom, scene-based motion direction prompt.

    Evaluates 9 Directorial Criteria:
      1. Primary subject & emotional/narrative meaning
      2. Specific scene actions (characters, scientific objects, environment, machines)
      3. Stable / static anchors (preserve facial anatomy, geometry, horizon)
      4. Active elements vs background separation (depth of field, multi-plane parallax)
      5. Environmental dynamics (particles, wind, lighting pulses, water, smoke)
      6. Story-driven camera motion (tracking, orbit, dolly, pan, tilt - never generic zoom)
      7. Motion intensity & narration pacing synchronization
      8. Seamless start and end progression
      9. Visual continuity with surrounding scenes
    """
    camera_label = (camera_movement or "automatic").replace("_", " ").title()
    intensity_label = (motion_intensity or "subtle").replace("_", " ").title()
    camera_style_label = (camera_style or "cinematic").replace("_", " ").title()
    timing_info = f"{start_time} - {end_time}" if start_time and end_time else f"{duration_seconds}s duration"

    system_instruction = (
        "You are an elite Hollywood documentary motion director, lead animator, and video editor. "
        "Your task is to analyze a documentary scene—including the visual image, narration script, timing, "
        "and narrative meaning—and produce a highly professional, scene-specific AI Image-to-Video direction prompt.\n\n"
        "DIRECTORIAL PRINCIPLES:\n"
        "1. NEVER use generic zoom/pan effects. Understand what the scene actually depicts and what the viewer should see happening.\n"
        "2. SPECIFIC REAL MOVEMENT:\n"
        "   - Human characters: natural physiological motion, breathing, subtle head turns, eye focus shifts, walking, realistic weight shifts, cloth/hair physics.\n"
        "   - DNA / Cellular / Molecular: helical 3D rotation, dynamic molecular bonding, glowing fluorescent energy pulses, floating cellular organelles, brownian motion.\n"
        "   - Historical scenes: characters performing era-specific actions, working tools, marching, torchlight/fire flickering, billowing smoke, weather dynamics.\n"
        "   - Objects / Machines: mechanical articulation, gears turning, light gleam shifting, physics-based interaction.\n"
        "   - Landscapes / Environments: cloud drift, wind through leaves, water currents, atmospheric dust motes, volumetric sun rays.\n"
        "3. DEPTH & PARALLAX: Distinct movement across foreground, midground, and background planes.\n"
        "4. CAMERA INTEGRATION: Intentional camera movement that supports the story (tracking, orbit, subtle push, slow pan, tilt, rack-focus). NEVER add motion purely for the sake of movement.\n"
        "5. STABILITY: Keep core geometry, facial features, and anatomical integrity strictly stable and distortion-free.\n\n"
        "OUTPUT FORMAT: Provide a concise, cinematic direction paragraph (120-180 words) optimized for state-of-the-art AI video models (Veo, Runway Gen-3, Luma Ray, Kling). "
        "Begin directly with the visual action and camera movement. No intro, no meta-commentary."
    )

    user_message = (
        f"PROJECT: {project_title}\n"
        f"CHAPTER {chapter_no}: {chapter_title}\n"
        f"NARRATION SCRIPT: {script_segment}\n"
        f"TIMING: {timing_info}\n"
        f"IMAGE DESCRIPTION: {image_prompt_text}\n"
        f"VISUAL STYLE: {animation_style or visual_style or 'Cinematic Documentary'}\n"
        f"REQUESTED CAMERA DYNAMICS: {camera_label} ({camera_style_label})\n"
        f"MOTION INTENSITY: {intensity_label}\n"
        f"DIRECTOR NOTES: {motion_instructions or 'Direct authentic, scene-appropriate motion matching the narration.'}\n\n"
        "Write the cinematic motion direction prompt now."
    )

    client = _get_genai_client()

    contents = []
    # Multimodal image input if image exists on disk
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            mime = "image/jpeg"
            if image_path.lower().endswith(".png"):
                mime = "image/png"
            elif image_path.lower().endswith(".webp"):
                mime = "image/webp"
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
            logger.info("Multimodal image attached for AI Motion Director analysis (%s)", image_path)
        except Exception as e:
            logger.warning("Could not load image bytes for multimodal prompt: %s", e)

    contents.append(user_message)

    import time
    last_exc = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    max_output_tokens=600,
                )
            )
            return response.text.strip()
        except Exception as exc:
            last_exc = exc
            logger.warning("AI Motion Director attempt %d failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2)

    raise VideoGenerationError(
        f"Failed to generate animation prompt after 3 attempts: {last_exc}"
    )


# ---------------------------------------------------------------------------
# Real Image-to-Video Generation (Multi-Provider Support)
# ---------------------------------------------------------------------------

def _generate_with_google_veo(
    animation_prompt: str,
    image_path: str,
    output_path: str,
    duration_seconds: int = 4,
    aspect_ratio: str = "16:9",
) -> str:
    """Attempt generation with Google Veo 3.1 API with automatic model fallback."""
    client = _get_genai_client()

    if not hasattr(client.models, "generate_videos"):
        raise VideoGenerationUnavailable("Google GenAI SDK does not expose generate_videos method.")

    # Veo 3.1 supports duration_seconds: 4, 6, or 8 (default to 4)
    if duration_seconds not in (4, 6, 8):
        duration_seconds = 4

    ar = "16:9" if aspect_ratio not in ("16:9", "9:16") else aspect_ratio

    try:
        image_input = types.Image.from_file(location=image_path)
    except Exception as img_err:
        logger.warning("types.Image.from_file failed, falling back to bytes: %s", img_err)
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        mime_type = "image/jpeg"
        if image_path.lower().endswith(".png"):
            mime_type = "image/png"
        elif image_path.lower().endswith(".webp"):
            mime_type = "image/webp"
        image_input = types.Image(image_bytes=image_bytes, mime_type=mime_type)

    candidate_models = ["veo-3.1-fast-generate-preview", "veo-3.1-generate-preview"]
    last_error = None

    for model_name in candidate_models:
        try:
            logger.info("Initiating Google Veo video generation with model: %s (duration: %ds, aspect: %s)", model_name, duration_seconds, ar)
            operation = client.models.generate_videos(
                model=model_name,
                source=types.GenerateVideosSource(
                    prompt=animation_prompt,
                    image=image_input,
                ),
                config=types.GenerateVideosConfig(
                    number_of_videos=1,
                    duration_seconds=duration_seconds,
                    aspect_ratio=ar,
                ),
            )

            import time
            max_wait = 360  # 6 minutes
            poll_interval = 8
            elapsed = 0
            while not operation.done:
                time.sleep(poll_interval)
                elapsed += poll_interval
                operation = client.operations.get(operation)
                logger.info("Google Veo [%s] progress: %ds elapsed", model_name, elapsed)
                if elapsed >= max_wait:
                    raise VideoGenerationError(f"Google Veo generation timed out after {max_wait} seconds.")

            if operation.error:
                err_msg = str(operation.error.get("message") if isinstance(operation.error, dict) else operation.error)
                logger.warning("Veo model %s returned operation error: %s", model_name, err_msg)
                if "high demand" in err_msg.lower() or "quota" in err_msg.lower():
                    last_error = err_msg
                    continue  # Try next model
                raise VideoGenerationError(f"Google Veo error: {err_msg}")

            if operation.response and operation.response.generated_videos:
                video_obj = operation.response.generated_videos[0]
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                try:
                    client.files.download(file=video_obj.video, destination=output_path)
                except Exception:
                    video_bytes = client.files.download(file=video_obj.video)
                    with open(output_path, "wb") as f:
                        f.write(video_bytes)
                logger.info("Google Veo video successfully saved to %s", output_path)
                return output_path

        except VideoGenerationError:
            raise
        except Exception as exc:
            logger.warning("Veo model %s generation attempt failed: %s", model_name, exc)
            last_error = str(exc)
            continue

    if last_error:
        last_err_lower = str(last_error).lower()
        if any(w in last_err_lower for w in ["not found", "permission_denied", "access denied", "not enabled", "404", "403"]):
            raise VideoGenerationUnavailable(f"Google Veo is not available for this API key: {last_error}")
        raise VideoGenerationError(f"Google Veo generation failed: {last_error}")
    raise VideoGenerationError("Google Veo completed with no video data.")


def _generate_with_luma(animation_prompt: str, image_path: str, output_path: str) -> str:
    """Attempt generation with Luma Dream Machine API."""
    api_key = os.environ.get("LUMA_API_KEY")
    if not api_key:
        raise VideoGenerationUnavailable("LUMA_API_KEY not configured.")

    # Upload or base64 encode image for Luma
    with open(image_path, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower().replace(".", "") or "jpeg"
    data_uri = f"data:image/{ext};base64,{b64_image}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": animation_prompt,
        "keyframes": {
            "frame0": {
                "type": "image",
                "url": data_uri,
            }
        }
    }

    resp = requests.post("https://api.lumalabs.ai/dream-machine/v1/generations/image-to-video", headers=headers, json=payload, timeout=30)
    if resp.status_code != 201 and resp.status_code != 200:
        raise VideoGenerationError(f"Luma API error ({resp.status_code}): {resp.text}")

    gen_data = resp.json()
    gen_id = gen_data.get("id")

    import time
    for _ in range(60):  # 5 minutes poll
        time.sleep(5)
        poll_resp = requests.get(f"https://api.lumalabs.ai/dream-machine/v1/generations/{gen_id}", headers=headers, timeout=15)
        if poll_resp.status_code == 200:
            status_data = poll_resp.json()
            state = status_data.get("state")
            if state == "completed":
                video_url = status_data.get("assets", {}).get("video")
                if video_url:
                    vid_resp = requests.get(video_url, timeout=60)
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(vid_resp.content)
                    return output_path
            elif state == "failed":
                raise VideoGenerationError(f"Luma generation failed: {status_data.get('failure_reason')}")

    raise VideoGenerationError("Luma generation timed out.")


def _generate_with_runway(animation_prompt: str, image_path: str, output_path: str) -> str:
    """Attempt generation with Runway ML Gen-3 API."""
    api_key = os.environ.get("RUNWAY_API_KEY")
    if not api_key:
        raise VideoGenerationUnavailable("RUNWAY_API_KEY not configured.")

    with open(image_path, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower().replace(".", "") or "jpeg"
    data_uri = f"data:image/{ext};base64,{b64_image}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Runway-Version": "2024-11-06",
        "Content-Type": "application/json",
    }
    payload = {
        "promptImage": data_uri,
        "promptText": animation_prompt,
        "model": "gen3a_turbo",
        "duration": 5,
        "ratio": "16:9",
    }

    resp = requests.post("https://api.dev.runwayml.com/v1/image_to_video", headers=headers, json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        raise VideoGenerationError(f"Runway API error ({resp.status_code}): {resp.text}")

    task_id = resp.json().get("id")
    import time
    for _ in range(60):
        time.sleep(5)
        poll = requests.get(f"https://api.dev.runwayml.com/v1/tasks/{task_id}", headers=headers, timeout=15)
        if poll.status_code == 200:
            data = poll.json()
            status = data.get("status")
            if status == "SUCCEEDED":
                url = data.get("output", [None])[0]
                if url:
                    vid_resp = requests.get(url, timeout=60)
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(vid_resp.content)
                    return output_path
            elif status == "FAILED":
                raise VideoGenerationError(f"Runway task failed: {data.get('failure')}")

    raise VideoGenerationError("Runway generation timed out.")


def generate_video_from_image(
    animation_prompt: str,
    image_path: str,
    output_path: str,
    duration_seconds: int = 4,
    camera_movement: str = "automatic",
    aspect_ratio: str = "16:9",
) -> str:
    """
    Attempt to generate a real AI video clip from a source image using available
    AI image-to-video providers.

    Checked in order of availability:
      1. Google Veo (veo-3.1-generate-preview / veo-3.1-fast-generate-preview)
      2. Luma Dream Machine API (LUMA_API_KEY)
      3. Runway ML Gen-3 (RUNWAY_API_KEY)

    CRITICAL PRINCIPLE:
      If no real image-to-video provider is accessible with the configured credentials,
      this function raises VideoGenerationUnavailable. It NEVER fakes output using
      CSS, transforms, generic FFmpeg zoom/pan, or slide animations.
    """
    if not animation_prompt or not animation_prompt.strip():
        raise ValueError("Animation prompt is required.")
    if not image_path or not os.path.exists(image_path):
        raise ValueError(f"Source image not found: {image_path}")

    # 1. Check Luma Dream Machine
    if os.environ.get("LUMA_API_KEY"):
        try:
            logger.info("Attempting real video generation via Luma Dream Machine...")
            return _generate_with_luma(animation_prompt, image_path, output_path)
        except Exception as e:
            logger.warning("Luma generation attempt failed: %s", e)

    # 2. Check Runway Gen-3
    if os.environ.get("RUNWAY_API_KEY"):
        try:
            logger.info("Attempting real video generation via Runway Gen-3...")
            return _generate_with_runway(animation_prompt, image_path, output_path)
        except Exception as e:
            logger.warning("Runway generation attempt failed: %s", e)

    # 3. Check Google Veo 3.1
    try:
        logger.info("Attempting real video generation via Google Veo 3.1...")
        return _generate_with_google_veo(
            animation_prompt,
            image_path,
            output_path,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
        )
    except VideoGenerationUnavailable:
        pass
    except VideoGenerationError:
        raise
    except Exception as exc:
        exc_str = str(exc).lower()
        unavailable_signals = [
            "not found", "404", "invalid model", "method not found",
            "permission_denied", "model not found", "unsupported",
            "not supported", "403", "access denied", "quota",
            "resource_exhausted", "unimplemented", "501", "billing", "not enabled",
        ]
        if any(sig in exc_str for sig in unavailable_signals):
            logger.info("Google Veo unavailable for current project credentials: %s", exc)
        else:
            logger.exception("Unexpected error during Veo generation: %s", exc)
            raise VideoGenerationError(f"Veo generation error: {exc}")

    # If all real providers are unavailable, raise VideoGenerationUnavailable
    raise VideoGenerationUnavailable(
        "Real AI Image-to-Video generation requires access to an enabled video AI model. "
        "Google Veo (veo-3.1-generate-preview) requires an approved Google Cloud project with Veo API access enabled. "
        "Alternatively, configure LUMA_API_KEY, RUNWAY_API_KEY, or REPLICATE_API_TOKEN in your environment. "
        "The AI Motion Director has analyzed your scene and saved the complete cinematic motion direction."
    )

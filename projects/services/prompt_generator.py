"""
projects/services/prompt_generator.py
--------------------------------------
AI Art Director — generates image and video prompts with full automated
creative direction. The user only sets aspect_ratio and video_quality;
everything else (style, mood, lighting, color, framing) is decided by the AI
after analyzing the project topic, chapter content and script.
"""
import os
import json
import time
import logging

from google import genai
from google.genai import types
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_genai_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set.")
    return genai.Client(api_key=api_key)


def _call_gemini(client, system_instruction: str, user_prompt: str,
                 json_mode: bool = True, temperature: float = 0.7,
                 max_tokens: int = 4096) -> str:
    """Retry wrapper around Gemini with exponential back-off."""
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    if json_mode:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        )

    last_exc = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=user_prompt,
                config=config,
            )
            return response.text
        except Exception as exc:
            last_exc = exc
            logger.warning("Gemini attempt %d failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Gemini failed after 3 attempts: {last_exc}")


def _extract_json(text: str) -> dict:
    """Robustly extract a JSON object from a Gemini response."""
    import re
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        try:
            text = json.loads(text)
        except Exception:
            pass
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"Could not parse JSON from response:\n{text[:300]}")


# ---------------------------------------------------------------------------
# Art Direction — called once and cached on the chapter
# ---------------------------------------------------------------------------

def _build_art_direction(chapter, aspect_ratio: str, visual_style_override: str = "") -> dict:
    """
    Ask Gemini to analyze the chapter and produce an autonomous art direction
    brief. Returns a dict with: visual_style, mood, lighting, color_palette,
    image_type, camera_style, composition_notes.
    """
    client = get_genai_client()

    try:
        script_text = chapter.script.script_text.strip()[:3000]
    except Exception:
        script_text = "(no script yet)"

    style_instruction = ""
    if visual_style_override:
        style_instruction = f"The user has mandated the visual style MUST be '{visual_style_override}'. Make sure the art direction strictly adheres to this style. "

    sys_instr = (
        "You are a world-class documentary cinematographer and AI art director. "
        "Analyze the provided chapter content and produce an autonomous creative "
        "brief for all images in this chapter. Your job is to make ALL creative "
        "decisions. " + style_instruction +
        "Return ONLY valid JSON with these exact keys: "
        "visual_style (string), mood (string), lighting (string), "
        "color_palette (string), image_type (string), camera_style (string), "
        "composition_notes (string)."
    )


    user_msg = (
        f"PROJECT: {chapter.project.title}\n"
        f"CHAPTER {chapter.chapter_no}: {chapter.title}\n"
        f"ASPECT RATIO: {aspect_ratio}\n"
        f"SCRIPT EXCERPT:\n{script_text}\n\n"
        "Produce the creative brief JSON now. Be specific and cinematic."
    )

    raw = _call_gemini(client, sys_instr, user_msg, json_mode=True, temperature=0.8)
    return _extract_json(raw)


# ---------------------------------------------------------------------------
# Image Prompts
# ---------------------------------------------------------------------------

def generate_image_prompts_for_chapter(chapter, visual_settings):
    """
    AI-directed image prompt generation. The AI autonomously determines all
    visual parameters and generates highly detailed prompts.
    """
    try:
        script_text = chapter.script.script_text.strip()
    except Exception:
        raise ValueError("No script found for this chapter.")
    if not script_text:
        raise ValueError("Chapter script is empty.")

    aspect_ratio = visual_settings.aspect_ratio or "16:9"
    images_per_minute = visual_settings.images_per_minute or 12

    # Step 1: Get autonomous art direction
    override_style = getattr(visual_settings, "visual_style", "")
    art = _build_art_direction(chapter, aspect_ratio, override_style)
    visual_style = art.get("visual_style", "Cinematic Documentary")

    mood = art.get("mood", "Serious")
    lighting = art.get("lighting", "Cinematic natural")
    color_palette = art.get("color_palette", "Muted desaturated tones")
    image_type = art.get("image_type", "Photorealistic")
    camera_style = art.get("camera_style", "Wide angle cinematic")
    composition_notes = art.get("composition_notes", "Rule of thirds, leading lines")

    # Step 2: Generate detailed prompts
    client = get_genai_client()

    sys_instr = (
        "You are an expert AI prompt engineer and documentary art director. "
        "Analyze the script and generate detailed image prompts for each visual moment. "
        "Each prompt must be richly detailed: subject, action, environment, composition, "
        "lighting, mood, depth of field, textures, and cinematic feel. "
        "DO NOT chunk text mechanically — identify real visual transitions. "
        "Respond ONLY with valid JSON."
    )

    user_msg = (
        f"PROJECT: {chapter.project.title}\n"
        f"CHAPTER {chapter.chapter_no}: {chapter.title}\n\n"
        f"ART DIRECTION BRIEF:\n"
        f"  Visual Style: {visual_style}\n"
        f"  Mood: {mood}\n"
        f"  Lighting: {lighting}\n"
        f"  Color Palette: {color_palette}\n"
        f"  Image Type: {image_type}\n"
        f"  Camera Style: {camera_style}\n"
        f"  Composition: {composition_notes}\n"
        f"  Aspect Ratio: {aspect_ratio}\n\n"
        f"SCRIPT:\n{script_text}\n\n"
        f"Generate roughly {images_per_minute} images per minute of script. "
        "Return JSON with a 'prompts' list. Each item must have: "
        "prompt_number (int), start_time (str '00:00'), end_time (str '00:05'), "
        "prompt_text (detailed cinematic string)."
    )

    raw = _call_gemini(client, sys_instr, user_msg, json_mode=True)
    data = _extract_json(raw)
    prompts_data = data.get("prompts", [])

    if not prompts_data:
        raise ValueError("No prompts returned by the AI.")

    from projects.models import ImagePrompt
    ImagePrompt.objects.filter(chapter=chapter).delete()

    saved = []
    for p in prompts_data:
        prompt = ImagePrompt.objects.create(
            project=chapter.project,
            chapter=chapter,
            prompt_number=p.get("prompt_number", len(saved) + 1),
            prompt_text=p.get("prompt_text", ""),
            start_time=p.get("start_time", ""),
            end_time=p.get("end_time", ""),
            visual_style=visual_style,
            image_type=image_type,
            mood=mood,
            lighting=lighting,
            color_palette=color_palette,
            aspect_ratio=aspect_ratio,
            status="Ready for generation",
        )
        saved.append(prompt)

    return saved


# ---------------------------------------------------------------------------
# Video Prompts
# ---------------------------------------------------------------------------

def generate_video_prompts_for_chapter(chapter, visual_settings):
    """
    AI-directed video prompt generation for chapters.
    """
    try:
        script_text = chapter.script.script_text.strip()
    except Exception:
        raise ValueError("No script found for this chapter.")
    if not script_text:
        raise ValueError("Chapter script is empty.")

    aspect_ratio = visual_settings.aspect_ratio or "16:9"

    art = _build_art_direction(chapter, aspect_ratio)
    visual_style = art.get("visual_style", "Cinematic Documentary")
    mood = art.get("mood", "Serious")
    camera_style = art.get("camera_style", "Wide angle cinematic")

    client = get_genai_client()

    sys_instr = (
        "You are an expert AI video prompt engineer and cinematic director. "
        "Analyze the script and generate detailed video prompts for a documentary. "
        "Emphasize motion: camera movements, subject motion, environmental motion. "
        "Return ONLY valid JSON."
    )

    user_msg = (
        f"PROJECT: {chapter.project.title}\n"
        f"CHAPTER {chapter.chapter_no}: {chapter.title}\n\n"
        f"ART DIRECTION: {visual_style}, {mood} mood, camera style: {camera_style}\n\n"
        f"SCRIPT:\n{script_text}\n\n"
        "Return JSON with a 'prompts' list. Each item must have: "
        "prompt_number (int), duration (str like '5 seconds'), "
        "start_time (str), end_time (str), "
        "prompt_text (detailed cinematic string), "
        "motion_description (str), camera_movement (str)."
    )

    raw = _call_gemini(client, sys_instr, user_msg, json_mode=True)
    data = _extract_json(raw)
    prompts_data = data.get("prompts", [])

    if not prompts_data:
        raise ValueError("No video prompts returned by the AI.")

    from projects.models import VideoPrompt
    VideoPrompt.objects.filter(chapter=chapter).delete()

    saved = []
    for p in prompts_data:
        prompt = VideoPrompt.objects.create(
            project=chapter.project,
            chapter=chapter,
            prompt_number=p.get("prompt_number", len(saved) + 1),
            prompt_text=p.get("prompt_text", ""),
            duration=p.get("duration", "5 seconds"),
            start_time=p.get("start_time", ""),
            end_time=p.get("end_time", ""),
            visual_style=visual_style,
            motion_description=p.get("motion_description", ""),
            camera_movement=p.get("camera_movement", ""),
            status="Ready for generation",
        )
        saved.append(prompt)

    return saved

"""
projects/services/audio_director.py
-------------------------------------
AI-driven audio design service.
Analyzes the full project script to autonomously select:
  - Background music style, tempo, and emotional arc
  - Sound effect cues keyed to narrative beats
  - Volume/ducking recommendations

NOTE: Actual audio file sourcing is deferred to the assembler.
This service produces a structured audio design brief (JSON) used
by video_assembler.py when rendering the final video.
"""

import os
import time
import json
import logging
import re

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is not set.")
    return genai.Client(api_key=api_key)


def _call_gemini(client, system_instruction: str, user_prompt: str) -> str:
    last_exc = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.75,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                ),
            )
            return response.text
        except Exception as exc:
            last_exc = exc
            logger.warning("AudioDirector Gemini attempt %d failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Gemini failed: {last_exc}")


def _extract_json(text: str) -> dict:
    text = text.strip()
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
# Public API
# ---------------------------------------------------------------------------

def generate_audio_brief(project) -> dict:
    """
    Analyzes the full project and generates a structured audio design brief.

    Returns a dict with:
        music_style     — e.g. "Orchestral documentary, brooding strings"
        music_tempo     — e.g. "Slow, 60 BPM"
        music_arc       — list of dicts: {chapter_no, intensity, note}
        sfx_cues        — list of dicts: {chapter_no, time, sound, description}
        vo_music_ratio  — float 0-1, volume ratio of music under VO (0.2 = 20%)
        music_genre     — e.g. "Cinematic orchestral"
        mood_keywords   — list of mood strings
    """
    client = _get_client()

    # Collect scripts
    chapters_text = []
    for ch in project.chapters.order_by("chapter_no"):
        try:
            script = ch.script.script_text.strip()[:1500]
        except Exception:
            script = "(no script)"
        chapters_text.append(f"Chapter {ch.chapter_no}: {ch.title}\n{script}")

    full_text = "\n\n---\n\n".join(chapters_text)[:8000]

    sys_instr = (
        "You are an expert documentary film composer and sound designer. "
        "Analyze the provided documentary script and produce a comprehensive audio design brief. "
        "Make ALL creative decisions autonomously. Return ONLY valid JSON."
    )

    user_msg = (
        f"PROJECT TITLE: {project.title}\n"
        f"TOTAL CHAPTERS: {len(chapters_text)}\n\n"
        f"SCRIPTS:\n{full_text}\n\n"
        "Produce an audio design brief JSON with these keys:\n"
        "  music_style (string): overall music style description\n"
        "  music_tempo (string): e.g. 'Slow, 60 BPM'\n"
        "  music_genre (string): genre label\n"
        "  mood_keywords (array of strings): 3-5 mood words\n"
        "  vo_music_ratio (float 0.0-0.3): music volume under voiceover\n"
        "  music_arc (array): [{chapter_no, intensity (0-10), note}]\n"
        "  sfx_cues (array): [{chapter_no, time_seconds, sound, description}]\n"
        "Be specific and cinematic."
    )

    raw = _call_gemini(client, sys_instr, user_msg)
    return _extract_json(raw)

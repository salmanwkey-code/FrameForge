"""
Gemini Text-to-Speech service for FrameForge.

Based on the tested working implementation from gemni-tts.py.
All API calls happen server-side. The API key is read from the
GOOGLE_API_KEY environment variable — never hardcoded.
"""

import os
import wave
import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# ── TTS Configuration ──────────────────────────────────────────────────
# Change these constants to switch voice/model without touching view code.
TTS_MODEL = "gemini-3.1-flash-tts-preview"
TTS_VOICE = "Kore"   # Tested and confirmed working voice name


# ── WAV helpers ────────────────────────────────────────────────────────

def _save_wav_file(filename: str, pcm_data: bytes,
                   channels: int = 1,
                   rate: int = 24000,
                   sample_width: int = 2) -> None:
    """
    Write raw PCM audio bytes to a playable WAV file.
    Parameters match the tested working implementation exactly.
    """
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_data)
    logger.info("WAV file saved: %s", filename)


# ── Public API ─────────────────────────────────────────────────────────

def generate_voiceover(script_text: str, output_path: str,
                       audio_profile: str = "", style: str = "Documentary",
                       pace: str = "Natural", accent: str = "British (RP)",
                       voice_name: str = TTS_VOICE) -> str:
    """
    Generate a WAV voiceover for the given script and save it to output_path.

    Args:
        script_text:  The chapter narration script (plain text, no markdown).
        output_path:  Absolute filesystem path where the .wav will be written.

    Returns:
        output_path  (the same path, confirmed written)

    Raises:
        ValueError:   If script_text is empty or the API key is missing.
        RuntimeError: If the Gemini API returns an unexpected response structure.
        OSError:      If the file cannot be written to output_path.
    """
    # ── Guard: empty script ───────────────────────────────────────────
    script_text = (script_text or "").strip()
    if not script_text:
        raise ValueError("Script text is empty. Generate a script first.")

    # ── Guard: API key ────────────────────────────────────────────────
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "API key is missing. Please configure GOOGLE_API_KEY in the environment."
        )

    # ── Gemini client ─────────────────────────────────────────────────
    # Initialised exactly as in the tested gemni-tts.py implementation.
    client = genai.Client(api_key=api_key)

    logger.info("Calling Gemini TTS (model=%s, voice=%s) ...", TTS_MODEL, TTS_VOICE)

    # ── Build TTS config helper ───────────────────────────────────────
    def _tts_config(vname):
        return types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=vname
                    )
                )
            )
        )

    # ── Attempt 1: minimal plain prompt (avoids safety triggers) ──────
    # Sending just the script text (no system instruction wrapper) is the
    # most reliable approach. The model reads it naturally as narration.
    audio_data = None
    attempts = [
        script_text,                                 # plain text only
        f"Read this text aloud:\n\n{script_text}",   # minimal prefix
    ]

    for i, prompt in enumerate(attempts):
        logger.info("TTS attempt %d ...", i + 1)
        try:
            response = client.models.generate_content(
                model=TTS_MODEL,
                contents=prompt,
                config=_tts_config(voice_name)
            )

            if not response.candidates:
                logger.warning("Attempt %d: no candidates returned.", i + 1)
                continue

            cand = response.candidates[0]
            finish = getattr(cand, "finish_reason", None)

            if str(finish) in ("FinishReason.SAFETY", "SAFETY"):
                logger.warning("Attempt %d blocked by safety filter.", i + 1)
                continue

            if not cand.content or not cand.content.parts:
                logger.warning("Attempt %d: candidate has no content parts. finish_reason=%s", i + 1, finish)
                continue

            data = cand.content.parts[0].inline_data.data
            if data:
                audio_data = data
                logger.info("TTS attempt %d succeeded.", i + 1)
                break
            else:
                logger.warning("Attempt %d: audio data is empty.", i + 1)

        except Exception as exc:
            logger.error("TTS attempt %d raised exception: %s", i + 1, exc)
            if i == len(attempts) - 1:
                raise RuntimeError(f"Voice generation failed after {len(attempts)} attempts: {exc}") from exc

    if not audio_data:
        raise RuntimeError(
            "Gemini TTS could not generate audio for this script. "
            "Try rephrasing the script or regenerating it first."
        )

    # ── Ensure output directory exists ────────────────────────────────
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ── Write WAV ─────────────────────────────────────────────────────
    _save_wav_file(output_path, audio_data)

    logger.info("Voiceover successfully written to: %s", output_path)
    return output_path

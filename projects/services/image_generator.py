import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Model constant
IMAGE_MODEL = "gemini-2.5-flash-image"

def generate_image(prompt_text: str, output_path: str, aspect_ratio: str = "16:9", quality: str = "1080p") -> str:
    prompt_text = (prompt_text or "").strip()
    if not prompt_text:
        raise ValueError("Prompt text is empty. Add a prompt first.")

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("API key is missing. Please configure GOOGLE_API_KEY in the environment.")

    # Enhance prompt based on quality setting
    if quality == "4K" and "4k" not in prompt_text.lower():
        enhanced_prompt = f"{prompt_text}, 4K UHD resolution, masterpiece, ultra-detailed, photorealistic"
    else:
        enhanced_prompt = prompt_text

    image_bytes = None
    try:
        client = genai.Client(api_key=api_key)
        logger.info("Calling Gemini Image Generation (model=%s, quality=%s, aspect=%s) ...", IMAGE_MODEL, quality, aspect_ratio)

        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=enhanced_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            )
        )

        for part in response.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                break

        if not image_bytes:
            raise RuntimeError("Generated image is empty.")

    except Exception as exc:
        logger.warning("Gemini image generation failed (%s). Falling back to Pollinations.ai...", exc)
        import requests
        import urllib.parse
        
        # Determine dimensions from aspect ratio and quality setting
        if quality == "720p":
            if aspect_ratio == "1:1":
                width, height = 720, 720
            elif aspect_ratio == "9:16":
                width, height = 720, 1280
            else:
                width, height = 1280, 720
        elif quality == "4K":
            if aspect_ratio == "1:1":
                width, height = 1440, 1440
            elif aspect_ratio == "9:16":
                width, height = 1440, 2560
            else:
                width, height = 2560, 1440
        else:  # default 1080p
            if aspect_ratio == "1:1":
                width, height = 1080, 1080
            elif aspect_ratio == "9:16":
                width, height = 1080, 1920
            else:
                width, height = 1920, 1080
            
        encoded_prompt = urllib.parse.quote(enhanced_prompt)
        # Using model=flux and enhance=true for high quality
        fallback_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true&model=flux&enhance=true"
        
        try:
            # Increase timeout to 120s for high-quality generations
            res = requests.get(fallback_url, timeout=120)
            res.raise_for_status()
            image_bytes = res.content
        except Exception as fallback_exc:
            raise RuntimeError(f"Primary API and fallback API both failed. Original error: {exc}") from fallback_exc

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(image_bytes)

    logger.info("Image successfully written to: %s", output_path)
    return output_path


def ensure_image_on_disk(generated_image) -> str:
    """
    Ensure the image file for generated_image exists on disk.
    If missing (e.g. wiped by an ephemeral container restart like on Render),
    regenerate it using the stored ImagePrompt metadata.
    """
    from django.conf import settings
    try:
        path = generated_image.image_file.path
    except Exception:
        path = os.path.join(str(settings.MEDIA_ROOT), str(generated_image.image_file.name))

    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    prompt = getattr(generated_image, "prompt", None)
    if not prompt or not prompt.prompt_text:
        return path

    try:
        from projects.models import ProjectVisualSettings
        project = generated_image.chapter.project
        vs = ProjectVisualSettings.objects.filter(project=project).first()
        aspect_ratio = (vs.aspect_ratio if vs and vs.aspect_ratio else None) or prompt.aspect_ratio or "16:9"
        quality = (vs.video_quality if vs and vs.video_quality else "1080p")

        style_parts = []
        if prompt.visual_style:
            style_parts.append(f"Visual style: {prompt.visual_style}")
        if prompt.image_type:
            style_parts.append(f"Image type: {prompt.image_type}")
        if prompt.mood:
            style_parts.append(f"Mood: {prompt.mood}")
        if prompt.lighting:
            style_parts.append(f"Lighting: {prompt.lighting}")
        if prompt.color_palette:
            style_parts.append(f"Color palette: {prompt.color_palette}")

        enriched_prompt = prompt.prompt_text.strip()
        if style_parts:
            style_string = ", ".join(style_parts)
            enriched_prompt = (
                f"CRITICAL INSTRUCTION: You MUST render this image strictly using these exact styles: {style_string}. "
                f"Completely IGNORE any visual, style, or medium instructions in the text below that contradict these styles. "
                f"The content to draw is: {prompt.prompt_text.strip()}"
            )

        logger.info("Auto-recovering missing image on disk: %s", path)
        generate_image(
            prompt_text=enriched_prompt,
            output_path=path,
            aspect_ratio=aspect_ratio,
            quality=quality,
        )
    except Exception as exc:
        logger.error("Failed to auto-recover image %s: %s", path, exc)

    return path


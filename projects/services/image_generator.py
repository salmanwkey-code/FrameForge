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

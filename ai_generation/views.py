import os
import json
import logging
import uuid
import shutil
from google import genai
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.conf import settings

from projects.models import (
    Project, Chapter, ChapterScript, Voiceover, ImagePrompt, VideoPrompt, GeneratedImage, ProjectVisualSettings
)
from projects.services.voice_generator import generate_voiceover as tts_generate_voiceover
from projects.services.voice_generator import TTS_VOICE
from projects.services.image_generator import generate_image
from projects.services.prompt_generator import generate_image_prompts_for_chapter, generate_video_prompts_for_chapter
from projects.utils import get_voiceover_filename, get_project_folder_name, get_chapter_folder_name

logger = logging.getLogger(__name__)

def generate_script_prompt(project, chapter, duration):
    """Generate prompt instructions for documentary script generation."""
    return (
        "You are an expert documentary scriptwriter. "
        "Write a documentary-style voiceover script for the following chapter.\n\n"
        f"PROJECT TITLE:\n{project.title}\n\n"
        f"PROJECT DESCRIPTION:\n{project.description}\n\n"
        f"PROJECT PROMPT:\n{project.prompt}\n\n"
        f"CHAPTER NUMBER:\n{chapter.chapter_no}\n\n"
        f"CHAPTER TITLE:\n{chapter.title}\n\n"
        f"CHAPTER SUMMARY:\n{chapter.summary}\n\n"
        f"REQUESTED SCRIPT LENGTH:\n{duration}\n\n"
        "Guidelines:\n"
        "- Natural spoken English.\n"
        "- Professional documentary style.\n"
        "- No headings inside the narration.\n"
        "- No bullet points.\n"
        "- No markdown.\n"
        "- No explanations about the generation process.\n"
        "- No \"Here is your script\".\n"
        "- No unnecessary introduction.\n"
        "- The output should be directly usable for text-to-speech.\n"
        "- Make the narration engaging and informative.\n"
        "- Stay focused on the chapter.\n"
        "- Do not repeat the chapter title unnecessarily.\n"
        "- Do not invent unrelated information.\n"
        "- Match the requested approximate duration.\n"
        "- Return ONLY the final voiceover script text."
    )


@login_required
def generate_chapter_script_api(request, project_id, chapter_id):
    """API endpoint to generate a chapter script via Gemini 3.6 Flash."""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method."}, status=405)

    try:
        project = Project.objects.get(id=project_id, user=request.user)
        chapter = Chapter.objects.get(id=chapter_id, project=project)
        
        data = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except Exception:
                data = request.POST.dict() if request.POST else {}
        duration = data.get("duration", "1 minute")
        
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return JsonResponse({"error": "Google API key is missing. Please configure GOOGLE_API_KEY in your environment."}, status=500)
            
        client = genai.Client(api_key=api_key)
        prompt = generate_script_prompt(project, chapter, duration)
        
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )
        
        script_text = response.text.strip()
        
        chapter_script, created = ChapterScript.objects.get_or_create(chapter=chapter)
        chapter_script.script_text = script_text
        chapter_script.duration = duration
        chapter_script.word_count = len(script_text.split())
        chapter_script.save()
        
        return JsonResponse({
            "success": True,
            "script": script_text,
            "duration": duration
        })
        
    except Project.DoesNotExist:
        return JsonResponse({"error": "Project not found."}, status=404)
    except Chapter.DoesNotExist:
        return JsonResponse({"error": "Chapter not found."}, status=404)
    except Exception as e:
        logger.exception("Failed to generate chapter script for chapter %s", chapter_id)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def generate_voiceover_api(request, project_id, chapter_id):
    """API endpoint to generate voiceover audio using Gemini TTS service."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        project = Project.objects.get(id=project_id, user=request.user)
        chapter = Chapter.objects.get(id=chapter_id, project=project)

        try:
            chapter_script = chapter.script
        except ChapterScript.DoesNotExist:
            return JsonResponse(
                {"error": "No script found. Generate a script first."},
                status=400
            )

        script_text = chapter_script.script_text.strip()
        if not script_text:
            return JsonResponse({"error": "The script is empty. Add content first."}, status=400)

        data = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except Exception:
                data = request.POST.dict() if request.POST else {}
        audio_profile = data.get("audio_profile", "")
        style = data.get("style", "Documentary")
        pace = data.get("pace", "Natural")
        accent = data.get("accent", "British (RP)")
        voice_name = data.get("voice_name", TTS_VOICE)

        voiceover, _ = Voiceover.objects.get_or_create(
            chapter=chapter,
            defaults={
                'provider': 'google_ai',
                'voice_name': voice_name,
                'status': 'pending',
            }
        )
        voiceover.status = 'generating'
        voiceover.voice_name = voice_name
        voiceover.audio_profile = audio_profile
        voiceover.style = style
        voiceover.pace = pace
        voiceover.accent = accent
        voiceover.save(update_fields=['status', 'voice_name', 'audio_profile', 'style', 'pace', 'accent'])

        project_folder = get_project_folder_name(project)
        chapter_folder = get_chapter_folder_name(chapter)
        
        voiceover_dir = os.path.join(
            settings.MEDIA_ROOT, "users", str(request.user.id),
            "projects", project_folder, chapter_folder,
        )
        os.makedirs(voiceover_dir, exist_ok=True)
        
        final_filename = get_voiceover_filename(chapter)
        final_abs_path = os.path.join(voiceover_dir, final_filename)
        
        temp_filename = f"temp_vo_{uuid.uuid4().hex}.wav"
        temp_abs_path = os.path.join(voiceover_dir, temp_filename)

        tts_generate_voiceover(
            script_text, temp_abs_path,
            audio_profile=audio_profile,
            style=style,
            pace=pace,
            accent=accent,
            voice_name=voice_name
        )

        if os.path.exists(final_abs_path):
            try:
                os.remove(final_abs_path)
            except OSError:
                pass
            
        shutil.move(temp_abs_path, final_abs_path)

        relative_path = os.path.join(
            "users", str(request.user.id), "projects",
            project_folder, chapter_folder, final_filename,
        ).replace("\\", "/")

        voiceover.audio_file.name = relative_path
        voiceover.status = 'completed'
        voiceover.script_hash_at_generation = chapter_script.script_hash
        voiceover.save()

        audio_url = settings.MEDIA_URL + relative_path
        return JsonResponse({"success": True, "audio_url": audio_url})

    except Exception as exc:
        logger.exception("Voiceover generation failed for chapter %s", chapter_id)
        Voiceover.objects.filter(chapter_id=chapter_id).update(status='failed')
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
def api_generate_image_prompts(request, project_id, chapter_id):
    """API endpoint to generate AI image prompts for a chapter."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)
        
    try:
        project = Project.objects.get(id=project_id, user=request.user)
        chapter = Chapter.objects.get(id=chapter_id, project=project)
        visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=project)
        
        saved_prompts = generate_image_prompts_for_chapter(chapter, visual_settings)
        prompts_data = [
            {
                "id": p.id,
                "prompt_number": p.prompt_number,
                "prompt_text": p.prompt_text,
                "start_time": p.start_time or "",
                "end_time": p.end_time or "",
            }
            for p in saved_prompts
        ]
        return JsonResponse({"success": True, "count": len(saved_prompts), "prompts": prompts_data})
    except Exception as e:
        logger.exception("Error generating image prompts")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def api_prepare_all_prompts(request, project_id):
    """Ensure prompts exist for all chapters in project."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)
    try:
        project = Project.objects.get(id=project_id, user=request.user)
        visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=project)
        chapters = project.chapters.order_by("chapter_no")
        all_prompts = []
        for ch in chapters:
            prompts = list(ImagePrompt.objects.filter(chapter=ch).order_by("prompt_number"))
            if not prompts:
                prompts = generate_image_prompts_for_chapter(ch, visual_settings)
            for p in prompts:
                all_prompts.append({
                    "id": p.id,
                    "chapter_id": ch.id,
                    "prompt_number": p.prompt_number,
                    "prompt_text": p.prompt_text,
                    "has_image": p.generated_images.exists()
                })
        return JsonResponse({"success": True, "prompts": all_prompts})
    except Exception as e:
        logger.exception("Failed to prepare all prompts for project %s", project_id)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def api_generate_video_prompts(request, project_id, chapter_id):
    """API endpoint to generate video/motion prompts for a chapter."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)
        
    try:
        project = Project.objects.get(id=project_id, user=request.user)
        chapter = Chapter.objects.get(id=chapter_id, project=project)
        visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=project)
        
        saved_prompts = generate_video_prompts_for_chapter(chapter, visual_settings)
        return JsonResponse({"success": True, "count": len(saved_prompts)})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def api_generate_image(request, prompt_id):
    """API endpoint to generate a single image from prompt."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        prompt = ImagePrompt.objects.get(id=prompt_id, project__user=request.user)
        project = prompt.project
        chapter = prompt.chapter

        existing_images = prompt.generated_images.all()
        for existing_image in existing_images:
            if existing_image.image_file:
                try:
                    file_path = existing_image.image_file.path
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass
            existing_image.delete()

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
            enriched_prompt = f"CRITICAL INSTRUCTION: You MUST render this image strictly using these exact styles: {style_string}. Completely IGNORE any visual, style, or medium instructions in the text below that contradict these styles. The content to draw is: {prompt.prompt_text.strip()}"

        project_folder = get_project_folder_name(project)
        chapter_folder = get_chapter_folder_name(chapter)

        images_dir = os.path.join(
            settings.MEDIA_ROOT, "users", str(request.user.id),
            "projects", project_folder, chapter_folder, "images"
        )
        os.makedirs(images_dir, exist_ok=True)

        image_no = prompt.prompt_number
        filename = f"image-{image_no:02d}.jpg"
        abs_path = os.path.join(images_dir, filename)

        vs = ProjectVisualSettings.objects.filter(project=project).first()
        aspect_ratio = (vs.aspect_ratio if vs and vs.aspect_ratio else None) or prompt.aspect_ratio or "16:9"
        quality = (vs.video_quality if vs and vs.video_quality else "1080p")
        generate_image(
            prompt_text=enriched_prompt,
            output_path=abs_path,
            aspect_ratio=aspect_ratio,
            quality=quality
        )

        relative_path = os.path.join(
            "users", str(request.user.id), "projects",
            project_folder, chapter_folder, "images", filename,
        ).replace("\\", "/")

        generated_img = GeneratedImage.objects.create(
            chapter=chapter,
            prompt=prompt,
            image_no=image_no,
            image_file=relative_path
        )

        prompt.status = "Generated"
        prompt.save()

        image_url = generated_img.image_file.url
        return JsonResponse({"success": True, "image_url": image_url, "image_id": generated_img.id})

    except ImagePrompt.DoesNotExist:
        return JsonResponse({"error": "Prompt not found."}, status=404)
    except Exception as e:
        logger.exception("Error generating image for prompt %s", prompt_id)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def api_save_prompt(request, prompt_id):
    """API endpoint to save edited prompt text."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)
        
    try:
        data = json.loads(request.body)
        prompt_type = data.get("type", "image")
        prompt_text = data.get("prompt_text", "")
        
        if prompt_type == "image":
            prompt = ImagePrompt.objects.get(id=prompt_id, project__user=request.user)
        else:
            prompt = VideoPrompt.objects.get(id=prompt_id, project__user=request.user)
            
        prompt.prompt_text = prompt_text
        prompt.save()
        
        return JsonResponse({"success": True})
    except (ImagePrompt.DoesNotExist, VideoPrompt.DoesNotExist):
        return JsonResponse({"error": "Prompt not found."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def api_save_visual_settings(request, project_id):
    """API endpoint to update visual settings for a project."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        project = Project.objects.get(id=project_id, user=request.user)
        data = json.loads(request.body)

        settings_obj, _ = ProjectVisualSettings.objects.get_or_create(project=project)
        if "visual_style" in data:
            settings_obj.visual_style = data["visual_style"]
        if "aspect_ratio" in data:
            settings_obj.aspect_ratio = data["aspect_ratio"]
            ImagePrompt.objects.filter(project=project).update(aspect_ratio=data["aspect_ratio"])
        if "video_quality" in data:
            settings_obj.video_quality = data["video_quality"]
        if "images_per_minute" in data:
            settings_obj.images_per_minute = data["images_per_minute"]
        settings_obj.save()

        return JsonResponse({"success": True})
    except Project.DoesNotExist:
        return JsonResponse({"error": "Project not found."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

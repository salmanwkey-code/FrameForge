import os
import re
import json
import shutil
import logging
from google import genai
from google.genai import types

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import JsonResponse

from .models import (
    Project, Chapter, ChapterScript, Voiceover, GeneratedImage, AnimatedVideo, ImagePrompt, VideoPrompt, ProjectVisualSettings
)
from .services.voice_generator import TTS_VOICE
from .utils import get_project_folder_name, get_chapter_folder_name

logger = logging.getLogger(__name__)

def extract_json(text):
    """
    Robustly extract a JSON object from a Gemini response.
    Handles: plain JSON, markdown-fenced JSON, extra text before/after.
    """
    text = text.strip()

    if text.startswith('"') and text.endswith('"'):
        try:
            text = json.loads(text)
        except Exception:
            pass

    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())

    raise ValueError(f"Could not extract valid JSON from Gemini response:\n{text[:300]}")


@login_required
def home(request):
    """User Dashboard displaying project metrics and recent activity."""
    projects = (
        Project.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )

    project_ids = projects.values_list('id', flat=True)
    chapter_count = Chapter.objects.filter(project_id__in=project_ids).count()
    script_count = ChapterScript.objects.filter(chapter__project_id__in=project_ids).exclude(script_text='').count()
    voiceover_count = Voiceover.objects.filter(chapter__project_id__in=project_ids, status='completed').count()
    image_count = GeneratedImage.objects.filter(chapter__project_id__in=project_ids).count()
    animated_count = AnimatedVideo.objects.filter(image_prompt__chapter__project_id__in=project_ids, status='generated').count()

    return render(
        request,
        "home.html",
        {
            "projects": projects,
            "chapter_count": chapter_count,
            "script_count": script_count,
            "voiceover_count": voiceover_count,
            "image_count": image_count,
            "animated_count": animated_count,
        }
    )


@login_required
def dashboard(request):
    return redirect("home")


@login_required
def projects(request):
    """List all projects owned by current user."""
    projects_qs = (
        Project.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )
    return render(request, "projects.html", {"projects": projects_qs})


@login_required
def create_project(request):
    """Interactive project creation wizard."""
    try:
        if request.method == "POST":
            action = request.POST.get("action", "generate")

            if action == "generate":
                prompt = request.POST.get("prompt")
                if prompt:
                    project = Project.objects.create(
                        user=request.user,
                        title="",
                        prompt=prompt,
                        description="",
                        tags=""
                    )

                    api_key = os.environ.get("GOOGLE_API_KEY")
                    if not api_key:
                        return render(request, "create_project.html", {"error": "GOOGLE_API_KEY is not configured in the environment."})
                        
                    client = genai.Client(api_key=api_key)

                    response = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            system_instruction=(
                                "You are a YouTube video planner. "
                                "Always respond with ONLY a valid JSON object — no markdown, no extra text. "
                                "The JSON must have these exact keys: "
                                "title (string), description (string), tags (list of strings), "
                                "chapters (list of objects with keys: chapter_title and summary)."
                            )
                        )
                    )

                    data = extract_json(response.text)

                    project.title = data.get("title", "")
                    project.description = data.get("description", "")
                    tags = data.get("tags", "")
                    if isinstance(tags, list):
                        project.tags = ", ".join(tags)
                    else:
                        project.tags = tags
                    project.save()

                    project_folder = get_project_folder_name(project)
                    folder_path = os.path.join(
                        settings.MEDIA_ROOT,
                        "users",
                        str(request.user.id),
                        "projects",
                        project_folder
                    )
                    os.makedirs(folder_path, exist_ok=True)
                    json_path = os.path.join(folder_path, "documentary.json")
                    with open(json_path, "w", encoding="utf-8") as file:
                        json.dump(data, file, indent=4, ensure_ascii=False)

                    for index, chapter_data in enumerate(data.get("chapters", []), start=1):
                        Chapter.objects.create(
                            project=project,
                            chapter_no=index,
                            title=chapter_data.get("chapter_title", ""),
                            summary=chapter_data.get("summary", "")
                        )

                    chapters = Chapter.objects.filter(project=project).order_by("chapter_no")
                    return render(
                        request,
                        "create_project.html",
                        {
                            "project": project,
                            "chapters": chapters,
                        }
                    )

            elif action == "save":
                project_id = request.POST.get("project_id")
                if project_id:
                    project = Project.objects.get(id=project_id, user=request.user)
                    project.prompt = request.POST.get("prompt", "")
                    project.title = request.POST.get("title", "")
                    project.description = request.POST.get("description", "")
                    project.tags = request.POST.get("tags", "")
                    project.save()

                    chapters = Chapter.objects.filter(project=project)
                    for chapter in chapters:
                        chapter.title = request.POST.get(f"chapter_title_{chapter.id}", "")
                        chapter.summary = request.POST.get(f"chapter_summary_{chapter.id}", "")
                        chapter.save()

                    return redirect("projects")

    except Exception as e:
        logger.exception("Error creating project")
        return render(request, "create_project.html", {"error": str(e)})

    return render(request, "create_project.html")


@login_required
def edit_project(request, project_id):
    """Project Details & Storyboard editor."""
    project = Project.objects.get(id=project_id, user=request.user)
    chapters = Chapter.objects.filter(project=project).order_by("chapter_no")

    if request.method == "POST":
        project.prompt = request.POST.get("prompt")
        project.title = request.POST.get("title")
        project.description = request.POST.get("description")
        project.tags = request.POST.get("tags")
        project.save()

        for chapter in chapters:
            chapter.title = request.POST.get(f"chapter_title_{chapter.id}")
            chapter.summary = request.POST.get(f"chapter_summary_{chapter.id}")
            chapter.save()
            
            script_text = request.POST.get(f"chapter_script_{chapter.id}")
            if script_text is not None:
                chapter_script, created = ChapterScript.objects.get_or_create(chapter=chapter)
                chapter_script.script_text = script_text
                chapter_script.word_count = len(script_text.split())
                chapter_script.save()

            audio_profile = request.POST.get(f"chapter_audio_profile_{chapter.id}")
            if audio_profile is not None:
                voiceover, _ = Voiceover.objects.get_or_create(
                    chapter=chapter,
                    defaults={'provider': 'google_ai', 'voice_name': TTS_VOICE, 'status': 'pending'}
                )
                voiceover.audio_profile = audio_profile
                voiceover.style = request.POST.get(f"chapter_style_{chapter.id}", "Documentary")
                voiceover.pace = request.POST.get(f"chapter_pace_{chapter.id}", "Natural")
                voiceover.accent = request.POST.get(f"chapter_accent_{chapter.id}", "British (RP)")
                voiceover.voice_name = request.POST.get(f"chapter_voice_{chapter.id}", TTS_VOICE)
                voiceover.save(update_fields=['audio_profile', 'style', 'pace', 'accent', 'voice_name'])

        return redirect("edit_project", project_id=project.id)

    for chapter in chapters:
        try:
            chapter.current_script = chapter.script.script_text
            chapter.current_duration = chapter.script.duration or "1 minute"
        except ChapterScript.DoesNotExist:
            chapter.current_script = ""
            chapter.current_duration = "1 minute"
            
        try:
            chapter.current_voiceover = chapter.voiceover
            try:
                chapter.current_voiceover_url = (
                    chapter.voiceover.audio_file.url
                    if chapter.voiceover.audio_file and chapter.voiceover.audio_file.name
                    else ""
                )
            except ValueError:
                chapter.current_voiceover_url = ""

            try:
                current_hash = chapter.script.script_hash
                vo_hash = chapter.voiceover.script_hash_at_generation
                chapter.voiceover_is_stale = (
                    bool(current_hash) and bool(vo_hash) and current_hash != vo_hash
                )
            except (ChapterScript.DoesNotExist, AttributeError):
                chapter.voiceover_is_stale = False
        except Voiceover.DoesNotExist:
            chapter.current_voiceover = None
            chapter.current_voiceover_url = ""
            chapter.voiceover_is_stale = False

    return render(
        request,
        "project_details.html",
        {
            "project": project,
            "chapters": chapters
        }
    )


@login_required
def delete_chapter(request, project_id, chapter_id):
    """Delete a chapter, renumber remaining chapters in DB, and rename disk folders."""
    if request.method == "POST":
        try:
            project = Project.objects.get(id=project_id, user=request.user)
            chapter = Chapter.objects.get(id=chapter_id, project=project)
            deleted_no = chapter.chapter_no

            try:
                project_folder = get_project_folder_name(project)
                chapter_folder = get_chapter_folder_name(chapter)
                chapter_dir = os.path.join(
                    settings.MEDIA_ROOT, "users", str(request.user.id),
                    "projects", project_folder, chapter_folder
                )
                if os.path.exists(chapter_dir):
                    shutil.rmtree(chapter_dir)
            except Exception:
                pass
                
            chapter.delete()

            # Renumber remaining chapters in DB and rename folders on disk
            remaining_chapters = Chapter.objects.filter(project=project, chapter_no__gt=deleted_no).order_by('chapter_no')
            for ch in remaining_chapters:
                old_folder_name = get_chapter_folder_name(ch)
                ch.chapter_no -= 1
                ch.save()
                new_folder_name = get_chapter_folder_name(ch)

                try:
                    project_folder = get_project_folder_name(project)
                    old_path = os.path.join(settings.MEDIA_ROOT, "users", str(request.user.id), "projects", project_folder, old_folder_name)
                    new_path = os.path.join(settings.MEDIA_ROOT, "users", str(request.user.id), "projects", project_folder, new_folder_name)
                    if os.path.exists(old_path) and not os.path.exists(new_path):
                        os.rename(old_path, new_path)
                except Exception:
                    pass

        except (Project.DoesNotExist, Chapter.DoesNotExist):
            pass
    return redirect("edit_project", project_id=project_id)


@login_required
def delete_project(request, project_id):
    """Delete a project and remove its user folder from media root."""
    if request.method == "POST":
        try:
            project = Project.objects.get(id=project_id, user=request.user)
            project_folder = get_project_folder_name(project)
            folder_path = os.path.join(
                settings.MEDIA_ROOT,
                "users",
                str(request.user.id),
                "projects",
                project_folder
            )
            if os.path.exists(folder_path):
                shutil.rmtree(folder_path)
            project.delete()
        except Project.DoesNotExist:
            pass
    return redirect("projects")

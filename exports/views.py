import os
import io
import zipfile
import logging
from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404, JsonResponse
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils.text import slugify

from projects.models import Project, Chapter, FinalVideo

logger = logging.getLogger(__name__)

@login_required
def export(request):
    """Exports overview page listing user projects ready for asset packaging."""
    projects = Project.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "export.html", {"projects": projects})


@login_required
def api_download_chapter_package(request, chapter_id):
    """
    Generate and stream a ZIP archive containing all assets for a single chapter:
    - Script (.txt)
    - Voiceover audio (.mp3/.wav)
    - All generated images
    - All animated video clips
    """
    try:
        chapter = Chapter.objects.get(id=chapter_id, project__user=request.user)
    except Chapter.DoesNotExist:
        raise Http404("Chapter not found")

    project = chapter.project
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        ch_prefix = f"CH{chapter.chapter_no:02d}"
        safe_chapter = f"{ch_prefix}_{slugify(chapter.title)[:35]}"

        # 1. Script
        try:
            if hasattr(chapter, 'script') and chapter.script.script_text:
                zf.writestr(f"{safe_chapter}/script/{ch_prefix}_Script.txt", chapter.script.script_text)
        except Exception:
            pass

        # 2. Voiceover
        try:
            if hasattr(chapter, 'voiceover') and chapter.voiceover.status == "completed" and chapter.voiceover.audio_file:
                abs_path = os.path.join(settings.MEDIA_ROOT, chapter.voiceover.audio_file.name)
                if os.path.exists(abs_path):
                    ext = os.path.splitext(chapter.voiceover.audio_file.name)[1] or ".mp3"
                    zf.write(abs_path, f"{safe_chapter}/voiceover/{ch_prefix}_VO{ext}")
        except Exception:
            pass

        # 3. Generated images
        image_prompts = chapter.image_prompts.order_by("prompt_number")
        for ip in image_prompts:
            generated = ip.generated_images.first()
            if generated and generated.image_file:
                abs_path = os.path.join(settings.MEDIA_ROOT, generated.image_file.name)
                if os.path.exists(abs_path):
                    ext = os.path.splitext(generated.image_file.name)[1] or ".jpg"
                    slug_hint = slugify(ip.prompt_text or f"scene_{ip.prompt_number}")[:25]
                    zf.write(abs_path, f"{safe_chapter}/images/{ch_prefix}_SC{ip.prompt_number:02d}_{slug_hint}{ext}")

        # 4. Animated video clips
        for ip in image_prompts:
            anim = ip.animated_videos.filter(status="generated").first()
            if anim and anim.video_file:
                abs_path = os.path.join(settings.MEDIA_ROOT, anim.video_file.name)
                if os.path.exists(abs_path):
                    slug_hint = slugify(ip.prompt_text or f"scene_{ip.prompt_number}")[:25]
                    zf.write(abs_path, f"{safe_chapter}/animated/{ch_prefix}_SC{ip.prompt_number:02d}_{slug_hint}.mp4")

    buffer.seek(0)
    zip_name = f"{slugify(project.title)[:30]}-{safe_chapter}.zip"
    response = HttpResponse(buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return response


@login_required
def api_download_project_package(request, project_id):
    """
    Generate and stream a ZIP archive containing ALL assets for every chapter
    in the project, organized into subfolders with NLE editor-friendly filenames.
    """
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        raise Http404("Project not found")

    chapters = Chapter.objects.filter(project=project).order_by("chapter_no")
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for chapter in chapters:
            ch_prefix = f"CH{chapter.chapter_no:02d}"
            safe_chapter = f"{ch_prefix}_{slugify(chapter.title)[:35]}"

            # Script
            try:
                if hasattr(chapter, 'script') and chapter.script.script_text:
                    zf.writestr(f"{safe_chapter}/script/{ch_prefix}_Script.txt", chapter.script.script_text)
            except Exception:
                pass

            # Voiceover
            try:
                if hasattr(chapter, 'voiceover') and chapter.voiceover.status == "completed" and chapter.voiceover.audio_file:
                    abs_path = os.path.join(settings.MEDIA_ROOT, chapter.voiceover.audio_file.name)
                    if os.path.exists(abs_path):
                        ext = os.path.splitext(chapter.voiceover.audio_file.name)[1] or ".mp3"
                        zf.write(abs_path, f"{safe_chapter}/voiceover/{ch_prefix}_VO{ext}")
            except Exception:
                pass

            # Images
            image_prompts = chapter.image_prompts.order_by("prompt_number")
            for ip in image_prompts:
                generated = ip.generated_images.first()
                if generated and generated.image_file:
                    abs_path = os.path.join(settings.MEDIA_ROOT, generated.image_file.name)
                    if os.path.exists(abs_path):
                        ext = os.path.splitext(generated.image_file.name)[1] or ".jpg"
                        slug_hint = slugify(ip.prompt_text or f"scene_{ip.prompt_number}")[:25]
                        zf.write(abs_path, f"{safe_chapter}/images/{ch_prefix}_SC{ip.prompt_number:02d}_{slug_hint}{ext}")

            # Animated videos
            for ip in image_prompts:
                anim = ip.animated_videos.filter(status="generated").first()
                if anim and anim.video_file:
                    abs_path = os.path.join(settings.MEDIA_ROOT, anim.video_file.name)
                    if os.path.exists(abs_path):
                        slug_hint = slugify(ip.prompt_text or f"scene_{ip.prompt_number}")[:25]
                        zf.write(abs_path, f"{safe_chapter}/animated/{ch_prefix}_SC{ip.prompt_number:02d}_{slug_hint}.mp4")

    buffer.seek(0)
    zip_name = f"{slugify(project.title)[:40]}-full-assets.zip"
    response = HttpResponse(buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return response


# ─────────────────────────────────────────────────────────────────────────────
# LEGACY RENDERING ENDPOINTS (Kept for backwards compatibility)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def final_render_page(request, project_id):
    """Legacy render page — redirects user to Asset Library production hub."""
    return redirect('asset_library', project_id=project_id)

@login_required
def api_render_final_video(request, project_id):
    return JsonResponse({'success': False, 'message': 'Final MP4 rendering is deprecated. Use Asset Library exports.'})

@login_required
def api_final_video_status(request, project_id):
    return JsonResponse({'status': 'deprecated', 'progress': 100})

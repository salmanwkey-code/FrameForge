import os
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from projects.models import (
    Project, Chapter, ProjectVisualSettings, ImagePrompt, GeneratedImage, AnimatedVideo, Voiceover
)

logger = logging.getLogger(__name__)

@login_required
def visual_studio(request, project_id=None):
    """Images & Videos asset manager view."""
    projects = Project.objects.filter(user=request.user).order_by("-created_at")

    selected_project = None
    if project_id:
        try:
            selected_project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return redirect("visual_studio")
    elif projects.exists():
        selected_project = projects.first()

    chapters = []
    visual_settings = None
    chapter_prompts = []

    if selected_project:
        chapters = Chapter.objects.filter(project=selected_project).order_by("chapter_no")
        visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=selected_project)

        for chapter in chapters:
            prompts = ImagePrompt.objects.filter(chapter=chapter).order_by("prompt_number")
            chapter_prompts.append({
                "chapter": chapter,
                "prompts": prompts,
            })

    context = {
        "projects": projects,
        "selected_project": selected_project,
        "chapters": chapters,
        "visual_settings": visual_settings,
        "chapter_prompts": chapter_prompts,
    }
    return render(request, "images_videos.html", context)


@login_required
def asset_library(request, project_id=None):
    """
    The central asset production hub for projects.
    If project_id is provided, shows all generated assets for that project.
    If project_id is None, shows a project selection grid with asset summary cards.
    """
    user_projects = Project.objects.filter(user=request.user).order_by("-created_at")

    if not project_id:
        projects_summary = []
        for p in user_projects:
            ch_list = p.chapters.all()
            scripts_count = 0
            vo_count = 0
            img_count = 0
            vid_count = 0
            for ch in ch_list:
                if hasattr(ch, 'script') and ch.script and ch.script.script_text.strip():
                    scripts_count += 1
                try:
                    if hasattr(ch, 'voiceover') and ch.voiceover.status == 'completed' and bool(getattr(ch.voiceover.audio_file, 'name', '')):
                        vo_count += 1
                except Exception:
                    pass
                for ip in ch.image_prompts.all():
                    try:
                        img = ip.generated_images.first()
                        if img and bool(getattr(img.image_file, 'name', '')):
                            img_count += 1
                    except Exception:
                        pass
                    try:
                        anim = ip.animated_videos.first() if hasattr(ip, 'animated_videos') else None
                        if anim and anim.status == 'generated' and bool(getattr(anim.video_file, 'name', '')):
                            vid_count += 1
                    except Exception:
                        pass

            total_assets = scripts_count + vo_count + img_count + vid_count
            projects_summary.append({
                "project": p,
                "chapter_count": ch_list.count(),
                "script_count": scripts_count,
                "vo_count": vo_count,
                "image_count": img_count,
                "video_count": vid_count,
                "total_assets": total_assets,
            })

        context = {
            "selected_project": None,
            "projects": user_projects,
            "projects_summary": projects_summary,
        }
        return render(request, "asset_library.html", context)

    # When project_id is provided
    try:
        selected_project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return redirect("asset_library_index")

    chapters = Chapter.objects.filter(project=selected_project).order_by("chapter_no")
    visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=selected_project)

    chapter_data = []
    total_images = 0
    total_voiceovers = 0
    total_videos = 0
    total_scripts = 0

    for ch in chapters:
        script_obj = getattr(ch, 'script', None)
        if script_obj and script_obj.script_text.strip():
            total_scripts += 1

        voiceover_obj = None
        try:
            if hasattr(ch, "voiceover") and ch.voiceover.status == "completed":
                if bool(getattr(ch.voiceover.audio_file, "name", "")):
                    voiceover_obj = ch.voiceover
                    total_voiceovers += 1
        except Exception:
            pass

        image_prompts = ch.image_prompts.order_by("prompt_number").prefetch_related("generated_images", "animated_videos")
        scene_data = []
        for ip in image_prompts:
            generated = None
            try:
                first_img = ip.generated_images.first()
                if first_img and bool(getattr(first_img.image_file, "name", "")):
                    generated = first_img
                    total_images += 1
            except Exception:
                pass

            anim_video = None
            try:
                first_vid = ip.animated_videos.first() if hasattr(ip, "animated_videos") else None
                if first_vid and first_vid.status == "generated" and bool(getattr(first_vid.video_file, "name", "")):
                    anim_video = first_vid
                    total_videos += 1
            except Exception:
                pass

            scene_data.append({
                "prompt": ip,
                "image": generated,
                "anim_video": anim_video,
            })

        chapter_data.append({
            "chapter": ch,
            "script": script_obj,
            "voiceover": voiceover_obj,
            "scenes": scene_data,
            "scene_count": len(scene_data),
            "image_count": sum(1 for s in scene_data if s["image"]),
            "video_count": sum(1 for s in scene_data if s["anim_video"]),
        })

    total_assets = total_scripts + total_voiceovers + total_images + total_videos

    context = {
        "selected_project": selected_project,
        "projects": user_projects,
        "chapters": chapters,
        "chapter_data": chapter_data,
        "visual_settings": visual_settings,
        "total_images": total_images,
        "total_voiceovers": total_voiceovers,
        "total_videos": total_videos,
        "total_scripts": total_scripts,
        "total_assets": total_assets,
        "total_chapters": chapters.count(),
    }
    return render(request, "asset_library.html", context)

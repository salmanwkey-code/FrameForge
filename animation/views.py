import os
import json
import logging
import threading
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import close_old_connections

from projects.models import (
    Project, Chapter, ProjectVisualSettings, ImagePrompt, VideoPrompt, GeneratedImage, AnimatedVideo
)
from projects.services.video_generator import (
    generate_animation_prompt,
    generate_video_from_image,
    extract_script_segment,
    VideoGenerationUnavailable,
    VideoGenerationError,
)
from projects.utils import get_project_folder_name, get_chapter_folder_name

logger = logging.getLogger(__name__)

@login_required
def animation_studio(request, project_id):
    """Render Veo Animation Studio page."""
    projects = Project.objects.filter(user=request.user).order_by("-created_at")
    
    try:
        selected_project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return redirect('visual_studio')
        
    chapters = Chapter.objects.filter(project=selected_project).order_by("chapter_no")
    visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=selected_project)
    
    image_prompts = ImagePrompt.objects.filter(project=selected_project).prefetch_related('generated_images').order_by("chapter__chapter_no", "prompt_number")
    video_prompts = VideoPrompt.objects.filter(project=selected_project).order_by("chapter__chapter_no", "prompt_number")
    
    animated_videos = AnimatedVideo.objects.filter(
        chapter__project=selected_project
    ).select_related('image_prompt', 'generated_image')
    
    animated_videos_map = {av.image_prompt_id: av for av in animated_videos}
    
    context = {
        'projects': projects,
        'selected_project': selected_project,
        'chapters': chapters,
        'visual_settings': visual_settings,
        'image_prompts': image_prompts,
        'video_prompts': video_prompts,
        'animated_videos_map': animated_videos_map,
    }
    
    return render(request, 'animation_studio.html', context)


@login_required
def api_generate_animation_prompt(request, image_id):
    """POST /api/generate-animation-prompt/<image_id>/"""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        generated_image = GeneratedImage.objects.select_related(
            'chapter__project', 'prompt'
        ).get(id=image_id, chapter__project__user=request.user)

        chapter = generated_image.chapter
        project = chapter.project
        image_prompt = generated_image.prompt

        data = json.loads(request.body) if request.body else {}
        try:
            duration_seconds = int(data.get("duration_seconds", 4))
        except (TypeError, ValueError):
            duration_seconds = 4
        if duration_seconds not in (4, 6, 8):
            duration_seconds = 4

        camera_movement   = data.get("camera_movement", "slow_zoom_in")
        motion_intensity  = data.get("motion_intensity", "subtle")
        animation_style   = data.get("animation_style", "")
        camera_style      = data.get("camera_style", "cinematic")
        motion_instructions = data.get("motion_instructions", "")

        visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=project)
        effective_style = animation_style or visual_settings.visual_style

        script_text = ""
        try:
            script_text = chapter.script.script_text
        except Exception:
            pass

        script_segment = extract_script_segment(
            script_text, image_prompt.start_time or "", image_prompt.end_time or ""
        )

        prompt_text = generate_animation_prompt(
            image_prompt_text=image_prompt.prompt_text,
            script_segment=script_segment,
            chapter_title=chapter.title,
            chapter_no=chapter.chapter_no,
            project_title=project.title,
            visual_style=effective_style,
            camera_movement=camera_movement,
            motion_intensity=motion_intensity,
            animation_style=effective_style,
            camera_style=camera_style,
            motion_instructions=motion_instructions,
            duration_seconds=duration_seconds,
            start_time=image_prompt.start_time or "",
            end_time=image_prompt.end_time or "",
        )

        return JsonResponse({
            "success": True,
            "animation_prompt": prompt_text,
            "script_segment": script_segment,
        })

    except GeneratedImage.DoesNotExist:
        return JsonResponse({"error": "Image not found or access denied."}, status=404)
    except Exception as exc:
        logger.exception("Error generating animation prompt for image %s", image_id)
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
def api_animate_image(request, image_id):
    """POST /api/animate-image/<image_id>/"""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        generated_image = GeneratedImage.objects.select_related(
            'chapter__project', 'prompt'
        ).get(id=image_id, chapter__project__user=request.user)

        chapter = generated_image.chapter
        project = chapter.project
        image_prompt = generated_image.prompt

        data = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except Exception:
                data = request.POST.dict() if request.POST else {}

        try:
            duration_seconds = int(data.get("duration_seconds", 4))
        except (TypeError, ValueError):
            duration_seconds = 4
        if duration_seconds not in (4, 6, 8):
            duration_seconds = 4

        camera_movement     = data.get("camera_movement", "slow_zoom_in")
        motion_intensity    = data.get("motion_intensity", "subtle")
        animation_style     = data.get("animation_style", "")
        camera_style        = data.get("camera_style", "cinematic")
        motion_instructions = data.get("motion_instructions", "")
        custom_animation_prompt = data.get("animation_prompt", "").strip()

        visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=project)
        effective_style = animation_style or visual_settings.visual_style

        script_text = ""
        try:
            script_text = chapter.script.script_text
        except Exception:
            pass
        script_segment = extract_script_segment(
            script_text, image_prompt.start_time or "", image_prompt.end_time or ""
        )

        image_path = ""
        try:
            if generated_image.image_file and os.path.exists(generated_image.image_file.path):
                image_path = generated_image.image_file.path
        except Exception:
            pass

        if not custom_animation_prompt:
            custom_animation_prompt = generate_animation_prompt(
                image_prompt_text=image_prompt.prompt_text,
                script_segment=script_segment,
                chapter_title=chapter.title,
                chapter_no=chapter.chapter_no,
                project_title=project.title,
                visual_style=effective_style,
                camera_movement=camera_movement,
                motion_intensity=motion_intensity,
                animation_style=effective_style,
                camera_style=camera_style,
                motion_instructions=motion_instructions,
                duration_seconds=duration_seconds,
                start_time=image_prompt.start_time or "",
                end_time=image_prompt.end_time or "",
                image_path=image_path,
            )

        animated_video, _ = AnimatedVideo.objects.get_or_create(
            image_prompt=image_prompt,
            defaults={
                "chapter": chapter,
                "generated_image": generated_image,
            }
        )
        animated_video.chapter = chapter
        animated_video.generated_image = generated_image
        animated_video.animation_prompt = custom_animation_prompt
        animated_video.script_segment = script_segment
        animated_video.duration_seconds = duration_seconds
        animated_video.camera_movement = camera_movement
        animated_video.motion_intensity = motion_intensity
        animated_video.animation_style = effective_style
        animated_video.camera_style = camera_style
        animated_video.motion_instructions = motion_instructions
        animated_video.status = "generating"
        animated_video.error_message = ""
        animated_video.save()

        try:
            image_path = generated_image.image_file.path
        except (ValueError, FileNotFoundError):
            animated_video.status = "failed"
            animated_video.error_message = "Source image file not found on disk."
            animated_video.save()
            return JsonResponse({"error": "Source image file is missing."}, status=400)

        project_folder = get_project_folder_name(project)
        chapter_folder = get_chapter_folder_name(chapter)
        image_no = image_prompt.prompt_number
        video_filename = f"image-{image_no:02d}-video.mp4"

        videos_dir = os.path.join(
            settings.MEDIA_ROOT, "users", str(request.user.id),
            "projects", project_folder, chapter_folder, "videos",
        )
        os.makedirs(videos_dir, exist_ok=True)
        output_path = os.path.join(videos_dir, video_filename)

        try:
            generate_video_from_image(
                animation_prompt=custom_animation_prompt,
                image_path=image_path,
                output_path=output_path,
                duration_seconds=duration_seconds,
                camera_movement=camera_movement,
                aspect_ratio=visual_settings.aspect_ratio if hasattr(visual_settings, 'aspect_ratio') else "16:9",
            )

            relative_path = os.path.join(
                "users", str(request.user.id), "projects",
                project_folder, chapter_folder, "videos", video_filename,
            ).replace("\\", "/")
            animated_video.video_file.name = relative_path
            animated_video.status = "generated"
            animated_video.save()

            video_url = settings.MEDIA_URL + relative_path
            return JsonResponse({
                "success": True,
                "video_url": video_url,
                "animation_prompt": custom_animation_prompt,
                "status": "generated",
            })

        except VideoGenerationUnavailable as exc:
            animated_video.status = "not_generated"
            animated_video.error_message = str(exc)
            animated_video.save()
            return JsonResponse({
                "success": False,
                "available": False,
                "animation_prompt": custom_animation_prompt,
                "error": str(exc),
                "message": str(exc),
                "status": "prompt_saved",
            }, status=200)

        except VideoGenerationError as exc:
            animated_video.status = "failed"
            animated_video.error_message = str(exc)
            animated_video.save()
            return JsonResponse({"error": str(exc)}, status=502)

    except GeneratedImage.DoesNotExist:
        return JsonResponse({"error": "Image not found or access denied."}, status=404)
    except Exception as exc:
        logger.exception("Error animating image %s", image_id)
        return JsonResponse({"error": "An unexpected error occurred."}, status=500)


@login_required
def api_animation_status(request, video_id):
    """GET /api/animation-status/<video_id>/"""
    try:
        animated_video = AnimatedVideo.objects.select_related(
            'chapter__project'
        ).get(id=video_id, chapter__project__user=request.user)

        video_url = ""
        if animated_video.video_file and animated_video.video_file.name:
            try:
                video_url = animated_video.video_file.url
            except Exception:
                pass

        return JsonResponse({
            "status": animated_video.status,
            "video_url": video_url,
            "animation_prompt": animated_video.animation_prompt,
            "error_message": animated_video.error_message if animated_video.status == "failed" else "",
        })
    except Exception:
        return JsonResponse({"error": "Not found."}, status=404)


@login_required
def api_batch_animate(request, project_id):
    """POST /api/batch-animate/<project_id>/"""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        project = Project.objects.get(id=project_id, user=request.user)
        visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=project)

        chapter_id = None
        image_ids = None
        if request.body:
            try:
                body_data = json.loads(request.body)
                chapter_id = body_data.get('chapter_id')
                image_ids = body_data.get('image_ids')
            except Exception:
                pass

        filter_kwargs = {'chapter__project': project}
        if chapter_id:
            filter_kwargs['chapter_id'] = chapter_id
        if image_ids:
            filter_kwargs['id__in'] = [int(i) for i in image_ids if str(i).isdigit()]

        all_images = GeneratedImage.objects.filter(
            **filter_kwargs
        ).select_related('chapter__project', 'prompt').order_by(
            'chapter__chapter_no', 'image_no'
        )

        images_to_animate = list(all_images)
        results = []
        unavailable_message = None

        for generated_image in images_to_animate:
            chapter = generated_image.chapter
            image_prompt = generated_image.prompt

            try:
                script_text = getattr(chapter.script, 'script_text', '') if hasattr(chapter, 'script') else ''
                script_segment = extract_script_segment(
                    script_text, image_prompt.start_time or "", image_prompt.end_time or ""
                )
                image_path = generated_image.image_file.path

                animation_prompt_text = generate_animation_prompt(
                    image_prompt_text=image_prompt.prompt_text,
                    script_segment=script_segment,
                    chapter_title=chapter.title,
                    chapter_no=chapter.chapter_no,
                    project_title=project.title,
                    visual_style=visual_settings.visual_style,
                    camera_movement="automatic",
                    motion_intensity="subtle",
                    animation_style=visual_settings.visual_style,
                    camera_style="cinematic",
                    motion_instructions="",
                    duration_seconds=4,
                    start_time=image_prompt.start_time or "",
                    end_time=image_prompt.end_time or "",
                    image_path=image_path,
                )

                animated_video, _ = AnimatedVideo.objects.get_or_create(
                    image_prompt=image_prompt,
                    defaults={"chapter": chapter, "generated_image": generated_image}
                )
                animated_video.chapter = chapter
                animated_video.generated_image = generated_image
                animated_video.animation_prompt = animation_prompt_text
                animated_video.script_segment = script_segment
                animated_video.duration_seconds = 4
                animated_video.status = "generating"
                animated_video.error_message = ""
                animated_video.save()

                project_folder = get_project_folder_name(project)
                chapter_folder = get_chapter_folder_name(chapter)
                video_filename = f"image-{image_prompt.prompt_number:02d}-video.mp4"
                videos_dir = os.path.join(
                    settings.MEDIA_ROOT, "users", str(request.user.id),
                    "projects", project_folder, chapter_folder, "videos",
                )
                os.makedirs(videos_dir, exist_ok=True)
                output_path = os.path.join(videos_dir, video_filename)

                generate_video_from_image(
                    animation_prompt=animation_prompt_text,
                    image_path=image_path,
                    output_path=output_path,
                    duration_seconds=4,
                    camera_movement="automatic",
                    aspect_ratio=getattr(visual_settings, 'aspect_ratio', "16:9"),
                )

                relative_path = os.path.join(
                    "users", str(request.user.id), "projects",
                    project_folder, chapter_folder, "videos", video_filename,
                ).replace("\\", "/")
                animated_video.video_file.name = relative_path
                animated_video.status = "generated"
                animated_video.save()

                results.append({
                    "image_id": generated_image.id,
                    "image_no": image_prompt.prompt_number,
                    "chapter_no": chapter.chapter_no,
                    "status": "generated",
                })

            except VideoGenerationUnavailable as exc:
                animated_video.status = "not_generated"
                animated_video.error_message = str(exc)
                animated_video.save()
                unavailable_message = str(exc)
                results.append({
                    "image_id": generated_image.id,
                    "image_no": image_prompt.prompt_number,
                    "chapter_no": chapter.chapter_no,
                    "status": "prompt_saved",
                    "message": "Animation prompt saved. Video generation unavailable.",
                })
            except Exception as exc:
                logger.exception("Batch animate error for image %s", generated_image.id)
                animated_video.status = "failed"
                animated_video.error_message = str(exc)
                animated_video.save()
                results.append({
                    "image_id": generated_image.id,
                    "image_no": image_prompt.prompt_number,
                    "chapter_no": chapter.chapter_no,
                    "status": "failed",
                })

        response_data = {
            "success": True,
            "total": len(images_to_animate),
            "results": results,
        }
        if unavailable_message:
            response_data["available"] = False
            response_data["message"] = unavailable_message

        return JsonResponse(response_data)

    except Project.DoesNotExist:
        return JsonResponse({"error": "Project not found."}, status=404)
    except Exception as exc:
        logger.exception("Batch animate error for project %s", project_id)
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
@require_POST
def api_generate_all_animations(request, project_id):
    """Background threading handler for generate all animations."""
    try:
        project = Project.objects.get(id=project_id, user=request.user)
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)

    visual_settings, _ = ProjectVisualSettings.objects.get_or_create(project=project)
    prompts_to_animate = ImagePrompt.objects.filter(
        project=project,
        generated_images__isnull=False
    ).select_related('chapter').distinct()

    if not prompts_to_animate.exists():
        return JsonResponse({
            'error': 'No generated images found in this project. Please generate images first.'
        }, status=400)

    user_id = request.user.id

    def generate_animations_worker():
        close_old_connections()
        for prompt in prompts_to_animate:
            try:
                gen_img = prompt.generated_images.first()
                if not gen_img or not gen_img.image_file:
                    continue
                image_path = gen_img.image_file.path
                if not os.path.exists(image_path):
                    continue
                chapter = prompt.chapter
                script_text = getattr(chapter.script, 'script_text', '') if hasattr(chapter, 'script') else ''
                script_segment = extract_script_segment(
                    script_text, prompt.start_time or "", prompt.end_time or ""
                )
                anim_prompt_text = generate_animation_prompt(
                    image_prompt_text=prompt.prompt_text,
                    script_segment=script_segment,
                    chapter_title=chapter.title,
                    chapter_no=chapter.chapter_no,
                    project_title=project.title,
                    visual_style=visual_settings.visual_style,
                    camera_movement="automatic",
                    motion_intensity="subtle",
                    animation_style=visual_settings.visual_style,
                    camera_style="cinematic",
                    motion_instructions="",
                    duration_seconds=4,
                    start_time=prompt.start_time or "",
                    end_time=prompt.end_time or "",
                    image_path=image_path,
                )

                av, _ = AnimatedVideo.objects.get_or_create(
                    image_prompt=prompt,
                    defaults={"chapter": chapter, "generated_image": gen_img}
                )
                av.chapter = chapter
                av.generated_image = gen_img
                av.animation_prompt = anim_prompt_text
                av.script_segment = script_segment
                av.duration_seconds = 4
                av.status = "generating"
                av.save()

                try:
                    project_folder = get_project_folder_name(project)
                    chapter_folder = get_chapter_folder_name(chapter)
                    video_filename = f"image-{prompt.prompt_number:02d}-video.mp4"
                    videos_dir = os.path.join(
                        settings.MEDIA_ROOT, "users", str(user_id),
                        "projects", project_folder, chapter_folder, "videos",
                    )
                    os.makedirs(videos_dir, exist_ok=True)
                    output_path = os.path.join(videos_dir, video_filename)

                    generate_video_from_image(
                        animation_prompt=anim_prompt_text,
                        image_path=image_path,
                        output_path=output_path,
                        duration_seconds=4,
                        camera_movement="automatic",
                        aspect_ratio=getattr(visual_settings, 'aspect_ratio', "16:9"),
                    )

                    relative_path = os.path.join(
                        "users", str(user_id), "projects",
                        project_folder, chapter_folder, "videos", video_filename,
                    ).replace("\\", "/")
                    av.video_file.name = relative_path
                    av.status = "generated"
                    av.save()

                except VideoGenerationUnavailable as exc:
                    av.status = "not_generated"
                    av.error_message = str(exc)
                    av.save()

                except Exception as exc:
                    av.status = "failed"
                    av.error_message = str(exc)
                    av.save()

            except Exception as outer_e:
                logger.exception("Outer worker exception for prompt %s", prompt.id)
            finally:
                close_old_connections()

    threading.Thread(target=generate_animations_worker, daemon=True).start()

    return JsonResponse({
        'success': True,
        'message': f'Animation queued for {len(prompts_to_animate)} scene(s)! Generating in background...',
        'total': len(prompts_to_animate),
    })

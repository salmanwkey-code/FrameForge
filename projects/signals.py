import os
import shutil
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from .models import Chapter, Voiceover, GeneratedImage, AnimatedVideo, FinalVideo
from django.conf import settings

@receiver(post_delete, sender=Voiceover)
def auto_delete_file_on_delete_voiceover(sender, instance, **kwargs):
    """
    Deletes file from filesystem
    when corresponding `Voiceover` object is deleted.
    """
    if instance.audio_file:
        if os.path.isfile(instance.audio_file.path):
            os.remove(instance.audio_file.path)

@receiver(post_delete, sender=GeneratedImage)
def auto_delete_file_on_delete_image(sender, instance, **kwargs):
    if instance.image_file:
        if os.path.isfile(instance.image_file.path):
            os.remove(instance.image_file.path)

@receiver(post_delete, sender=AnimatedVideo)
def auto_delete_file_on_delete_video(sender, instance, **kwargs):
    if instance.video_file:
        if os.path.isfile(instance.video_file.path):
            os.remove(instance.video_file.path)

@receiver(post_delete, sender=FinalVideo)
def auto_delete_file_on_delete_final_video(sender, instance, **kwargs):
    if instance.video_file:
        if os.path.isfile(instance.video_file.path):
            os.remove(instance.video_file.path)

@receiver(post_delete, sender=Chapter)
def auto_delete_chapter_folder_on_delete(sender, instance, **kwargs):
    """
    Deletes the entire chapter folder from filesystem
    when corresponding `Chapter` object is deleted.
    """
    from django.utils.text import slugify
    project = instance.project
    title_slug = slugify(project.title) if project.title else 'untitled-project'
    project_folder = title_slug[:50].rstrip('-')
    chapter_title_slug = slugify(instance.title) if instance.title else 'untitled-chapter'
    chapter_folder_name = f"Chapter {instance.chapter_no} - {chapter_title_slug[:50].rstrip('-')}"
    
    chapter_path = os.path.join(
        settings.MEDIA_ROOT,
        'users',
        str(project.user_id),
        'projects',
        project_folder,
        chapter_folder_name
    )
    
    if os.path.isdir(chapter_path):
        try:
            shutil.rmtree(chapter_path)
        except Exception as e:
            print(f"Error removing chapter directory: {e}")

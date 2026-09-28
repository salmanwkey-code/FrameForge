
# Create your models here.
import os
# pyrefly: ignore [missing-import]
from django.db import models
# pyrefly: ignore [missing-import]
from django.contrib.auth.models import User
# pyrefly: ignore [missing-import]
from django.conf import settings



class Project(models.Model):
    STATUS_CHOICES = [
        ('accepted', 'Accepted'),
        ('not_accepted', 'Not Accepted'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='projects'
    )

    title = models.CharField(max_length=255, blank=True)
    prompt = models.TextField()
    description = models.TextField(blank=True)
    tags = models.TextField(blank=True)
    plan_json = models.JSONField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='not_accepted'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    

    def __str__(self):
        return self.title
    
class Chapter(models.Model):
    project = models.ForeignKey(
        'Project',
        on_delete=models.CASCADE,
        related_name='chapters'
    )

    chapter_no = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    summary = models.TextField()

    status = models.CharField(
        max_length=20,
        default='draft'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Chapter {self.chapter_no}: {self.title}"

class ChapterScript(models.Model):
    chapter = models.OneToOneField(
        'Chapter',
        on_delete=models.CASCADE,
        related_name='script'
    )

    script_text = models.TextField()
    word_count = models.PositiveIntegerField(default=0)
    # Hash of script_text — used to detect edits after voiceover generation
    script_hash = models.CharField(max_length=64, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    duration = models.CharField(max_length=50, blank=True, null=True)

    def save(self, *args, **kwargs):
        import hashlib
        self.script_hash = hashlib.sha256(self.script_text.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Script - Chapter {self.chapter.chapter_no}"


class ImagePrompt(models.Model):
    project = models.ForeignKey(
        'Project',
        on_delete=models.CASCADE,
        related_name='image_prompts',
        null=True
    )
    chapter = models.ForeignKey(
        'Chapter',
        on_delete=models.CASCADE,
        related_name='image_prompts'
    )

    prompt_number = models.PositiveIntegerField(default=1)
    prompt_text = models.TextField()
    start_time = models.CharField(max_length=20, blank=True, null=True)
    end_time = models.CharField(max_length=20, blank=True, null=True)
    visual_style = models.CharField(max_length=100, blank=True, default='')
    image_type = models.CharField(max_length=100, blank=True, default='')
    mood = models.CharField(max_length=100, blank=True, default='')
    lighting = models.CharField(max_length=100, blank=True, default='')
    color_palette = models.CharField(max_length=100, blank=True, default='')
    aspect_ratio = models.CharField(max_length=20, blank=True, default='16:9')
    status = models.CharField(max_length=50, default='Ready for generation')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Image Prompt {self.prompt_number} - Chapter {self.chapter.chapter_no}"

class VideoPrompt(models.Model):
    project = models.ForeignKey(
        'Project',
        on_delete=models.CASCADE,
        related_name='video_prompts'
    )
    chapter = models.ForeignKey(
        'Chapter',
        on_delete=models.CASCADE,
        related_name='video_prompts'
    )
    prompt_number = models.PositiveIntegerField(default=1)
    prompt_text = models.TextField()
    duration = models.CharField(max_length=20, blank=True, null=True)
    start_time = models.CharField(max_length=20, blank=True, null=True)
    end_time = models.CharField(max_length=20, blank=True, null=True)
    visual_style = models.CharField(max_length=100, blank=True, default='')
    motion_description = models.TextField(blank=True, default='')
    camera_movement = models.TextField(blank=True, default='')
    status = models.CharField(max_length=50, default='Ready for generation')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Video Prompt {self.prompt_number} - Chapter {self.chapter.chapter_no}"

class ProjectVisualSettings(models.Model):
    project = models.OneToOneField(
        'Project',
        on_delete=models.CASCADE,
        related_name='visual_settings'
    )
    QUALITY_CHOICES = [
        ('720p', '720p'),
        ('1080p', '1080p'),
        ('4K', '4K'),
    ]
    visual_style = models.CharField(max_length=100, blank=True, default='')
    video_quality = models.CharField(max_length=20, choices=QUALITY_CHOICES, default='1080p')
    aspect_ratio = models.CharField(max_length=20, blank=True, default='16:9')
    images_per_minute = models.PositiveIntegerField(default=12)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Visual Settings - {self.project.title}"


def voiceover_upload_path(instance, filename):
    from django.utils.text import slugify
    project = instance.chapter.project
    title_slug = slugify(project.title) if project.title else 'untitled-project'
    project_folder = title_slug[:50].rstrip('-')
    chapter = instance.chapter
    chapter_title_slug = slugify(chapter.title) if chapter.title else 'untitled-chapter'
    chapter_folder = f"Chapter {chapter.chapter_no} - {chapter_title_slug[:50].rstrip('-')}"
    return os.path.join(
        'users',
        str(project.user_id),
        'projects',
        project_folder,
        chapter_folder,
        'voiceovers',
        filename,
    ).replace('\\', '/')


class Voiceover(models.Model):

    PROVIDERS = (
        ('google_ai', 'Google AI Studio'),
        ('elevenlabs', 'ElevenLabs'),
        ('other', 'Other'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('generating', 'Generating'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    chapter = models.OneToOneField(
        'Chapter',
        on_delete=models.CASCADE,
        related_name='voiceover'
    )

    provider = models.CharField(
        max_length=50,
        choices=PROVIDERS
    )

    voice_name = models.CharField(max_length=100)
    
    audio_profile = models.TextField(blank=True, default='')
    
    style = models.CharField(
        max_length=50,
        blank=True,
        default='Documentary'
    )
    
    pace = models.CharField(
        max_length=50,
        blank=True,
        default='Natural'
    )
    
    accent = models.CharField(
        max_length=50,
        blank=True,
        default='British (RP)'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    audio_file = models.FileField(
        upload_to=voiceover_upload_path,
        blank=True
    )

    # Hash of the script at time of generation — used to detect staleness
    script_hash_at_generation = models.CharField(max_length=64, blank=True, default='')

    duration_seconds = models.PositiveIntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"Voiceover - Chapter {self.chapter.chapter_no}"



def generated_image_upload_path(instance, filename):
    from django.utils.text import slugify
    project = instance.chapter.project
    title_slug = slugify(project.title) if project.title else 'untitled-project'
    project_folder = title_slug[:50].rstrip('-')
    chapter = instance.chapter
    chapter_title_slug = slugify(chapter.title) if chapter.title else 'untitled-chapter'
    chapter_folder = f"Chapter {chapter.chapter_no} - {chapter_title_slug[:50].rstrip('-')}"
    return os.path.join(
        'users',
        str(project.user_id),
        'projects',
        project_folder,
        chapter_folder,
        'images',
        filename,
    ).replace('\\', '/')


class GeneratedImage(models.Model):
    chapter = models.ForeignKey(
        'Chapter',
        on_delete=models.CASCADE,
        related_name='generated_images'
    )

    prompt = models.ForeignKey(
        ImagePrompt,
        on_delete=models.CASCADE,
        related_name='generated_images'
    )

    image_no = models.PositiveIntegerField()

    image_file = models.ImageField(
        upload_to=generated_image_upload_path
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Image {self.image_no} - Chapter {self.chapter.chapter_no}"



class ChapterExport(models.Model):
    chapter = models.OneToOneField(
        'Chapter',
        on_delete=models.CASCADE,
        related_name='export'
    )

    zip_file = models.FileField(
        upload_to='chapter_exports/'
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Export - Chapter {self.chapter.chapter_no}"


def animated_video_upload_path(instance, filename):
    """
    Store animated videos inside the correct project/chapter folder.
    e.g. users/<uid>/projects/<project-slug>/Chapter 1 - <slug>/videos/<filename>
    """
    # pyrefly: ignore [missing-import]
    from django.utils.text import slugify
    project = instance.chapter.project
    title_slug = slugify(project.title) if project.title else 'untitled-project'
    project_folder = title_slug[:50].rstrip('-')
    chapter = instance.chapter
    chapter_title_slug = slugify(chapter.title) if chapter.title else 'untitled-chapter'
    chapter_folder = f"Chapter {chapter.chapter_no} - {chapter_title_slug[:50].rstrip('-')}"
    return os.path.join(
        'users',
        str(project.user_id),
        'projects',
        project_folder,
        chapter_folder,
        'videos',
        filename,
    ).replace('\\', '/')


class AnimatedVideo(models.Model):
    STATUS_CHOICES = [
        ('not_generated', 'Not Generated'),
        ('generating', 'Generating'),
        ('generated', 'Generated'),
        ('failed', 'Failed'),
    ]

    CAMERA_MOVEMENT_CHOICES = [
        ('slow_zoom_in', 'Slow Zoom In'),
        ('slow_zoom_out', 'Slow Zoom Out'),
        ('pan_left', 'Pan Left'),
        ('pan_right', 'Pan Right'),
        ('tilt_up', 'Tilt Up'),
        ('tilt_down', 'Tilt Down'),
        ('dolly_in', 'Dolly In'),
        ('dolly_out', 'Dolly Out'),
        ('orbit', 'Orbit'),
        ('static_cinematic', 'Static Cinematic'),
        ('handheld', 'Handheld'),
        ('automatic', 'Automatic'),
    ]

    MOTION_INTENSITY_CHOICES = [
        ('subtle', 'Subtle'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('strong', 'Strong'),
    ]

    CAMERA_STYLE_CHOICES = [
        ('cinematic', 'Cinematic'),
        ('documentary', 'Documentary'),
        ('dynamic', 'Dynamic'),
        ('static', 'Static'),
        ('smooth', 'Smooth'),
        ('dramatic', 'Dramatic'),
    ]

    chapter = models.ForeignKey(
        'Chapter',
        on_delete=models.CASCADE,
        related_name='animated_videos'
    )
    image_prompt = models.ForeignKey(
        'ImagePrompt',
        on_delete=models.CASCADE,
        related_name='animated_videos'
    )
    generated_image = models.ForeignKey(
        'GeneratedImage',
        on_delete=models.CASCADE,
        related_name='animated_videos'
    )

    # The AI-generated animation prompt text
    animation_prompt = models.TextField(blank=True, default='')
    # The script segment corresponding to this image's time slot
    script_segment = models.TextField(blank=True, default='')

    # Animation settings chosen by user
    duration_seconds = models.PositiveIntegerField(default=4)
    camera_movement = models.CharField(
        max_length=50,
        choices=CAMERA_MOVEMENT_CHOICES,
        default='slow_zoom_in'
    )
    motion_intensity = models.CharField(
        max_length=20,
        choices=MOTION_INTENSITY_CHOICES,
        default='subtle'
    )
    animation_style = models.CharField(max_length=100, blank=True, default='')
    camera_style = models.CharField(
        max_length=50,
        choices=CAMERA_STYLE_CHOICES,
        default='cinematic'
    )
    motion_instructions = models.TextField(blank=True, default='')

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='not_generated'
    )

    video_file = models.FileField(
        upload_to=animated_video_upload_path,
        blank=True,
        null=True
    )

    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # One video per image prompt (one current animation)
        unique_together = [('image_prompt',)]

    def __str__(self):
        return f"AnimatedVideo {self.image_prompt.prompt_number} - Chapter {self.chapter.chapter_no}"

def final_video_upload_path(instance, filename):
    from django.utils.text import slugify
    project = instance.project
    title_slug = slugify(project.title) if project.title else 'untitled-project'
    project_folder = title_slug[:50].rstrip('-')
    return os.path.join(
        'users',
        str(project.user_id),
        'projects',
        project_folder,
        'exports',
        filename,
    ).replace('\\', '/')

class FinalVideo(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assembling', 'Assembling'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    project = models.OneToOneField(
        'Project',
        on_delete=models.CASCADE,
        related_name='final_video'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    video_file = models.FileField(
        upload_to=final_video_upload_path,
        blank=True,
        null=True
    )

    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Final Video - {self.project.title}"


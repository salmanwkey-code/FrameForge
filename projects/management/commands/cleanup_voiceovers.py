import os
import re
import shutil
from django.core.management.base import BaseCommand
from django.conf import settings
from projects.models import Chapter, Voiceover
from projects.utils import get_voiceover_filename, get_project_folder_name, get_chapter_folder_name

class Command(BaseCommand):
    help = 'Cleans up and renames existing voiceover files to the new sanitized folder format based on chapter number and title.'

    def handle(self, *args, **options):
        users_dir = os.path.join(settings.MEDIA_ROOT, 'users')
        if not os.path.exists(users_dir):
            self.stdout.write(self.style.WARNING(f"Media users directory not found at {users_dir}"))
            return

        self.stdout.write(self.style.NOTICE("Starting voiceover folder cleanup..."))
        renamed_count = 0
        orphan_count = 0

        # Regex to match old filenames: chapter_<id>_voiceover.wav
        # or the recent chapter_01_slug.wav
        old_pattern = re.compile(r'^chapter_(\d+)_voiceover\.wav$')
        recent_pattern = re.compile(r'^chapter_(\d+)_.*\.wav$')

        for vo in Voiceover.objects.select_related('chapter', 'chapter__project').all():
            if not vo.audio_file or not vo.audio_file.name:
                continue

            old_file_path = os.path.join(settings.MEDIA_ROOT, vo.audio_file.name)
            if not os.path.exists(old_file_path):
                self.stdout.write(self.style.WARNING(f"File missing for Voiceover Chapter {vo.chapter.chapter_no}: {old_file_path}"))
                continue

            chapter = vo.chapter
            project = chapter.project

            project_folder = get_project_folder_name(project)
            chapter_folder = get_chapter_folder_name(chapter)
            final_filename = get_voiceover_filename(chapter)

            new_relative_path = os.path.join(
                "users",
                str(project.user.id),
                "projects",
                project_folder,
                chapter_folder,
                final_filename
            ).replace("\\", "/")

            if vo.audio_file.name == new_relative_path:
                # Already in correct place
                continue

            new_file_path = os.path.join(settings.MEDIA_ROOT, new_relative_path)
            
            # Move the file physically
            os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
            if os.path.exists(new_file_path):
                os.remove(new_file_path)
            shutil.move(old_file_path, new_file_path)

            # Update DB
            vo.audio_file.name = new_relative_path
            vo.save()

            self.stdout.write(self.style.SUCCESS(f"Migrated: {old_file_path} -> {new_file_path}"))
            renamed_count += 1

        self.stdout.write(self.style.SUCCESS(f"\nMigration completed. Migrated: {renamed_count}"))


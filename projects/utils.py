import os
from django.utils.text import slugify

def get_project_folder_name(project):
    """
    Generate a clean, human-readable folder name for a project.
    E.g. 'how-human-height-is-determined'
    """
    title_slug = slugify(project.title) if project.title else "untitled-project"
    return title_slug[:50].rstrip('-')

def get_chapter_folder_name(chapter):
    """
    Generate a clean, human-readable folder name for a chapter.
    E.g. 'Chapter 1 - how-genetics-determines-height'
    """
    title_slug = slugify(chapter.title) if chapter.title else "untitled-chapter"
    return f"Chapter {chapter.chapter_no} - {title_slug[:50].rstrip('-')}"

def get_voiceover_filename(chapter):
    """
    Returns the constant name for the voiceover file inside the chapter folder.
    """
    return "voiceover.wav"

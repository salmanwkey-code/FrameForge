import os
import sys
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.conf import settings
from projects.models import (
    Project, Chapter, Voiceover, GeneratedImage, AnimatedVideo
)

def staff_required(view_func):
    """Decorator ensuring only staff or superusers can access custom admin panel."""
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_staff and not request.user.is_superuser:
            raise PermissionDenied("Staff authorization required to access FrameForge Admin Panel.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@staff_required
def admin_dashboard(request):
    """Main FrameForge Administration Dashboard."""
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    total_projects = Project.objects.count()
    total_chapters = Chapter.objects.count()
    total_images = GeneratedImage.objects.count()
    total_voiceovers = Voiceover.objects.filter(status='completed').count()
    total_animations = AnimatedVideo.objects.filter(status='generated').count()
    
    recent_projects = Project.objects.select_related('user').order_by('-created_at')[:10]
    recent_users = User.objects.order_by('-date_joined')[:10]

    # Simple system health metrics
    db_status = "Connected"
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as e:
        db_status = f"Error: {str(e)}"

    has_google_key = bool(os.environ.get("GOOGLE_API_KEY"))

    context = {
        "total_users": total_users,
        "active_users": active_users,
        "total_projects": total_projects,
        "total_chapters": total_chapters,
        "total_images": total_images,
        "total_voiceovers": total_voiceovers,
        "total_animations": total_animations,
        "recent_projects": recent_projects,
        "recent_users": recent_users,
        "system_health": {
            "django_version": "6.0.6",
            "python_version": sys.version.split()[0],
            "database": db_status,
            "ai_key_configured": has_google_key,
            "media_root": str(settings.MEDIA_ROOT),
        }
    }
    return render(request, "admin_panel/dashboard.html", context)


@staff_required
def admin_users(request):
    """User Management panel (No passwords/keys shown)."""
    search_query = request.GET.get('q', '').strip()
    users = User.objects.all().order_by('-date_joined')
    if search_query:
        users = users.filter(username__icontains=search_query) | users.filter(email__icontains=search_query)

    user_list = []
    for user in users:
        user_list.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'is_active': user.is_active,
            'date_joined': user.date_joined,
            'project_count': Project.objects.filter(user=user).count(),
        })

    return render(request, "admin_panel/users.html", {"users": user_list, "query": search_query})


@staff_required
def toggle_staff_status(request, user_id):
    """Toggle is_staff permission for a target user."""
    if request.method == "POST":
        target_user = get_object_or_404(User, pk=user_id)
        if target_user == request.user:
            messages.error(request, "You cannot modify your own admin permissions.")
        else:
            target_user.is_staff = not target_user.is_staff
            target_user.save()
            status_str = "granted Admin access" if target_user.is_staff else "revoked Admin access"
            messages.success(request, f"Successfully {status_str} for user '{target_user.username}'.")
    return redirect('admin_users')


@staff_required
def admin_projects(request):
    """Project Overview panel."""
    search_query = request.GET.get('q', '').strip()
    projects_qs = Project.objects.select_related('user').order_by('-created_at')
    if search_query:
        projects_qs = projects_qs.filter(title__icontains=search_query) | projects_qs.filter(prompt__icontains=search_query)

    return render(request, "admin_panel/projects.html", {"projects": projects_qs, "query": search_query})


@staff_required
def admin_activity(request):
    """Generation Activity log."""
    recent_images = GeneratedImage.objects.select_related('chapter__project').order_by('-created_at')[:15]
    recent_voiceovers = Voiceover.objects.select_related('chapter__project').order_by('-updated_at')[:15]
    recent_animations = AnimatedVideo.objects.select_related('chapter__project').order_by('-updated_at')[:15]

    context = {
        "recent_images": recent_images,
        "recent_voiceovers": recent_voiceovers,
        "recent_animations": recent_animations,
    }
    return render(request, "admin_panel/activity.html", context)

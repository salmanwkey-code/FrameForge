"""
URL configuration for FrameForge project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django default admin (for superuser technical management)
    path('django-admin/', admin.site.urls),

    # Public pages (landing, robots.txt, sitemap.xml)
    path('', include('core.urls')),

    # Authentication (login, signup, logout, profile)
    path('', include('accounts.urls')),

    # Project management (create, edit, delete, chapters)
    path('', include('projects.urls')),

    # AI Generation (script, voiceover, image prompts)
    path('', include('ai_generation.urls')),

    # Assets (images & videos page, asset library)
    path('', include('assets.urls')),

    # Animation (Veo animation studio)
    path('', include('animation.urls')),

    # Exports (chapter ZIP, project ZIP, legacy render redirect)
    path('', include('exports.urls')),

    # FrameForge Custom Admin Panel (staff-only)
    path('admin-panel/', include('admin_panel.urls')),
]

import os
import logging
from django.urls import re_path
from django.views.static import serve

logger = logging.getLogger(__name__)

def media_serve_with_recovery(request, path, document_root=None):
    if not document_root:
        document_root = str(settings.MEDIA_ROOT)
    full_path = os.path.join(document_root, path)
    if os.path.exists(full_path):
        return serve(request, path, document_root=document_root)

    try:
        from projects.models import GeneratedImage
        from projects.services.image_generator import ensure_image_on_disk

        norm_path = path.replace('\\', '/')
        img = GeneratedImage.objects.filter(image_file__endswith=norm_path).first()
        if not img:
            filename = os.path.basename(path)
            img = GeneratedImage.objects.filter(image_file__endswith=filename).first()

        if img:
            recovered_path = ensure_image_on_disk(img)
            if recovered_path and os.path.exists(recovered_path):
                return serve(request, path, document_root=document_root)
    except Exception as exc:
        logger.warning("Could not auto-recover media file %s: %s", path, exc)

    return serve(request, path, document_root=document_root)

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', media_serve_with_recovery, {'document_root': str(settings.MEDIA_ROOT)}),
]


# Custom error handlers
handler404 = 'core.views.custom_404'
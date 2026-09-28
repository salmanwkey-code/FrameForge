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

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )

# Custom error handlers
handler404 = 'core.views.custom_404'
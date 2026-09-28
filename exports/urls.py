from django.urls import path
from . import views

urlpatterns = [
    path('exports/', views.export, name='exports'),
    path('api/download-chapter-package/<int:chapter_id>/', views.api_download_chapter_package, name='api_download_chapter_package'),
    path('api/download-project-package/<int:project_id>/', views.api_download_project_package, name='api_download_project_package'),
    path('visuals/<int:project_id>/render/', views.final_render_page, name='final_render_page'),
    path('api/render-final-video/<int:project_id>/', views.api_render_final_video, name='api_render_final_video'),
    path('api/final-video-status/<int:project_id>/', views.api_final_video_status, name='api_final_video_status'),
]

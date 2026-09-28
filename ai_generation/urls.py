from django.urls import path
from . import views

urlpatterns = [
    path('project/<int:project_id>/generate_script/<int:chapter_id>/', views.generate_chapter_script_api, name='generate_chapter_script_api'),
    path('project/<int:project_id>/generate_voiceover/<int:chapter_id>/', views.generate_voiceover_api, name='generate_voiceover_api'),
    path('api/visual-settings/<int:project_id>/', views.api_save_visual_settings, name='api_save_visual_settings'),
    path('api/generate-image-prompts/<int:project_id>/<int:chapter_id>/', views.api_generate_image_prompts, name='api_generate_image_prompts'),
    path('api/prepare-all-prompts/<int:project_id>/', views.api_prepare_all_prompts, name='api_prepare_all_prompts'),
    path('api/generate-video-prompts/<int:project_id>/<int:chapter_id>/', views.api_generate_video_prompts, name='api_generate_video_prompts'),
    path('api/generate-image/<int:prompt_id>/', views.api_generate_image, name='api_generate_image'),
    path('api/save-prompt/<int:prompt_id>/', views.api_save_prompt, name='api_save_prompt'),
]

from django.urls import path
from . import views

urlpatterns = [
    path('visuals/<int:project_id>/animation/', views.animation_studio, name='animation_studio'),
    path('api/generate-animation-prompt/<int:image_id>/', views.api_generate_animation_prompt, name='api_generate_animation_prompt'),
    path('api/animate-image/<int:image_id>/', views.api_animate_image, name='api_animate_image'),
    path('api/animation-status/<int:video_id>/', views.api_animation_status, name='api_animation_status'),
    path('api/batch-animate/<int:project_id>/', views.api_batch_animate, name='api_batch_animate'),
    path('api/generate-all-animations/<int:project_id>/', views.api_generate_all_animations, name='api_generate_all_animations'),
]

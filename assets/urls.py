from django.urls import path
from . import views

urlpatterns = [
    path('visuals/', views.visual_studio, name='visual_studio'),
    path('visuals/<int:project_id>/', views.visual_studio, name='visual_studio_project'),
    path('asset-library/', views.asset_library, name='asset_library_index'),
    path('asset-library/<int:project_id>/', views.asset_library, name='asset_library'),
]

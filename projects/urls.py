from django.urls import path
from . import views

urlpatterns = [
    path('home/', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('projects/', views.projects, name='projects'),
    path('create_project/', views.create_project, name='create_project'),
    path('project/<int:project_id>/', views.edit_project, name='edit_project'),
    path('project/<int:project_id>/delete/', views.delete_project, name='delete_project'),
    path('project/<int:project_id>/delete_chapter/<int:chapter_id>/', views.delete_chapter, name='delete_chapter'),
]

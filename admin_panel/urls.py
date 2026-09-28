from django.urls import path
from . import views

urlpatterns = [
    path('', views.admin_dashboard, name='admin_dashboard'),
    path('users/', views.admin_users, name='admin_users'),
    path('users/<int:user_id>/toggle-staff/', views.toggle_staff_status, name='toggle_staff_status'),
    path('projects/', views.admin_projects, name='admin_projects'),
    path('activity/', views.admin_activity, name='admin_activity'),
]

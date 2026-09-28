from django.db import models
import os
from django.conf import settings

def profile_picture_upload_path(instance, filename):
    extension = filename.split(".")[-1]

    return os.path.join(
        "users",
        f"{instance.user.id}",
        "profile",
        f"profile.{extension}"
    )    
class Profile(models.Model):
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to=profile_picture_upload_path, blank=True, null=True)
    full_name = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return self.user.username

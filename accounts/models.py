import os
import time
from django.conf import settings
from django.db import models


def profile_picture_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext not in ["jpg", "jpeg", "png", "webp", "gif"]:
        ext = "png"
    timestamp = int(time.time())
    return f"users/{instance.user.id}/profile/avatar_{timestamp}.{ext}"


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

    @property
    def avatar_url(self):
        """Return the URL of the profile picture if the file exists on storage, else None."""
        if self.profile_picture and self.profile_picture.name:
            try:
                storage = self.profile_picture.storage
                if storage.exists(self.profile_picture.name):
                    return self.profile_picture.url
            except Exception:
                pass
        return None

    @property
    def initials(self):
        """Return the uppercase initial for display in the default avatar circle."""
        name = self.display_name or self.full_name or self.user.username or "U"
        return name[0].upper()


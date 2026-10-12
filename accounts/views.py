import os

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required

from .models import Profile

def login_page(request):

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect("home")

        return render(
            request,
            "login.html",
            {
                "error": "Invalid username or password"
            }
        )

    return render(request, "login.html")


def signup_page(request):

    if request.method == "POST":

        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if password != confirm_password:
            return render(
                request,
                "signup.html",
                {
                    "error": "Passwords do not match"
                }
            )

        if User.objects.filter(username=username).exists():
            return render(
                request,
                "signup.html",
                {
                    "error": "Username already exists"
                }
            )

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )

        # Create user folders
        user_folder = os.path.join(
            settings.MEDIA_ROOT,
            "users",
            f"{user.id}"
        )

        folders = [
            "profile",
            "projects"
        ]

        for folder in folders:
            os.makedirs(
                os.path.join(user_folder, folder),
                exist_ok=True
            )

        login(request, user)

        return redirect("home")

    return render(request, "signup.html")


@login_required
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        profile_obj.full_name = request.POST.get("full_name", "").strip()
        profile_obj.display_name = request.POST.get("display_name", "").strip()
        email = request.POST.get("email", "").strip()
        profile_obj.phone_number = request.POST.get("phone_number", "").strip()
        profile_obj.bio = request.POST.get("bio", "").strip()

        if email:
            profile_obj.email = email
            if request.user.email != email:
                request.user.email = email
                request.user.save(update_fields=["email"])

        uploaded_file = request.FILES.get("profile_picture")
        if uploaded_file:
            MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB
            ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

            ext = os.path.splitext(uploaded_file.name)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                messages.error(request, "Invalid image format. Allowed formats: JPG, PNG, WEBP, GIF.")
                return redirect("profile")

            if uploaded_file.size > MAX_UPLOAD_SIZE:
                messages.error(request, "Image file too large. Maximum size is 5MB.")
                return redirect("profile")

            try:
                from PIL import Image
                img = Image.open(uploaded_file)
                img.verify()
                uploaded_file.seek(0)
            except Exception:
                messages.error(request, "Uploaded file is not a valid image.")
                return redirect("profile")

            # Remove previous profile picture file from disk if it exists
            if profile_obj.profile_picture and profile_obj.profile_picture.name:
                try:
                    storage = profile_obj.profile_picture.storage
                    if storage.exists(profile_obj.profile_picture.name):
                        storage.delete(profile_obj.profile_picture.name)
                except Exception:
                    pass

            profile_obj.profile_picture = uploaded_file

        profile_obj.save()
        messages.success(request, "Profile updated successfully.")
        return redirect("profile")

    return render(
        request,
        "user_profile.html",
        {
            "profile": profile_obj
        }
    )

def logout_user(request):
    logout(request)
    return redirect("login")

import os

from django.conf import settings
from django.shortcuts import render, redirect
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

    profile_obj, created = Profile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":

        profile_obj.full_name = request.POST.get("full_name")
        profile_obj.email = request.POST.get("email")
        profile_obj.phone_number = request.POST.get("phone_number")
        profile_obj.bio = request.POST.get("bio")
        profile_obj.display_name = request.POST.get("display_name")

        if request.FILES.get("profile_picture"):
            profile_obj.profile_picture = request.FILES["profile_picture"]

        profile_obj.save()

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

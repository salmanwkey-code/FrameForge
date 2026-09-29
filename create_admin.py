import os
import django

# Sets up the Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yts_agent.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = "admin"
email = "[salman.wkey@gamil.com]"
password = "[salman.wlock]"

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print(f"Superuser '{username}' created successfully!")
else:
    print(f"Superuser '{username}' already exists.")

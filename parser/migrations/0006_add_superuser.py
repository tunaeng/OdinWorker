import os
from django.db import migrations

def create_superuser(apps, schema_editor):
    User = apps.get_model('auth', 'User') 

    username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin')

    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )

class Migration(migrations.Migration):

    dependencies = [
        ('parser', '0005_add_task_to_lecture_presentation'), 
    ]

    operations = [
        migrations.RunPython(create_superuser),
    ]

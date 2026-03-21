from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Let's try a different username to be 100% sure
        username = 'railway_admin'
        password = 'NewPassword123!'
        email = 'admin@example.com'

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username, email, password)
            self.stdout.write(self.style.SUCCESS(f'CREATED: {username}'))
        else:
            self.stdout.write(self.style.WARNING(f'EXISTS: {username}'))

import os
import django
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount

User = get_user_model()

class Command(BaseCommand):
    help = 'Clean up orphaned social accounts'

    def handle(self, *args, **options):
        self.stdout.write('Starting cleanup of orphaned social accounts...')
        
        orphaned_count = 0
        for social_account in SocialAccount.objects.all():
            try:
                # Try to access the user
                user = social_account.user
                if user:
                    self.stdout.write(f'✓ Social account {social_account.uid} has valid user: {user.email}')
            except User.DoesNotExist:
                self.stdout.write(f'✗ Found orphaned social account: {social_account.uid}')
                social_account.delete()
                orphaned_count += 1
                self.stdout.write(f'✓ Deleted orphaned social account: {social_account.uid}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Cleanup completed. Removed {orphaned_count} orphaned social accounts.')
        )
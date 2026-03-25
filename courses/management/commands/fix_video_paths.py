from django.core.management.base import BaseCommand
from courses.models import VideoMetadata
from django.conf import settings

class Command(BaseCommand):
    help = 'Fix video file paths for existing VideoMetadata objects'

    def handle(self, *args, **options):
        videos = VideoMetadata.objects.filter(video_type='upload')
        fixed_count = 0
        
        for video in videos:
            if video.video_file:
                old_path = str(video.video_file)
                print(f"Original path: {old_path}")  # <== ADD THIS LINE
                
                # Clean up the path
                if old_path.startswith(settings.MEDIA_URL):
                    new_path = old_path[len(settings.MEDIA_URL):]
                elif old_path.startswith('/media/'):
                    new_path = old_path[7:]
                else:
                    new_path = old_path
                
                if new_path != old_path:
                    video.video_file = new_path
                    video.save()
                    fixed_count += 1
                    self.stdout.write(f"Fixed: {old_path} -> {new_path}")
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully fixed {fixed_count} video paths')
        )
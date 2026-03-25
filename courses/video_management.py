# views.py - Updated video handling views

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import json
import logging
import os
from .models import Chapter, Course, VideoMetadata
from .forms import VideoForm
from .ai_integration.youtube_fetcher import fetch_youtube_videos
from .ai_integration.ai_module import summarize_video

logger = logging.getLogger(__name__)

def add_video(request, chapter_id):
    """Add video to a specific chapter (existing functionality)"""
    chapter = get_object_or_404(Chapter, id=chapter_id)
    course = chapter.course

    if request.method == "POST":
        form = VideoForm(request.POST, request.FILES)
        if form.is_valid():
            video_type = form.cleaned_data['video_type']
            title = form.cleaned_data['title']
            description = form.cleaned_data['description']

            if video_type == 'youtube':
                youtube_url = form.cleaned_data['youtube_url']
                video = VideoMetadata.objects.create(
                    chapter=chapter,
                    course=course,
                    video_type='youtube',
                    title=title,
                    description=description,
                    youtube_url=youtube_url,
                    relevance_point="Main Content"
                )
            else:
                video_file = form.cleaned_data['video_file']
                video = VideoMetadata.objects.create(
                    chapter=chapter,
                    course=course,
                    video_type='upload',
                    title=title,
                    description=description,
                    video_file=video_file,
                    relevance_point="Main Content"
                )

            messages.success(request, "Video added successfully!")
            return redirect(reverse("courses:view_course", kwargs={"pk": course.id}))
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = VideoForm()

    context = {
        "form": form,
        "chapter": chapter,
        "course": course,
    }
    return render(request, "add_video.html", context)



@require_http_methods(["POST"])
@csrf_exempt
def upload_video_to_chapter(request, chapter_id):
    """Handle video file uploads for a specific chapter"""
    try:
        chapter = get_object_or_404(Chapter, id=chapter_id)
        logger.info(f"Processing video upload for chapter {chapter_id}")
        
        if not request.FILES.get('video'):
            return JsonResponse({"status": "error", "message": "No video file provided"}, status=400)

        video_file = request.FILES['video']
        title = request.POST.get('title', video_file.name)
        description = request.POST.get('description', '')
        
        # Validate file type
        allowed_extensions = ['mp4', 'mov', 'avi', 'mkv', 'webm']
        file_extension = video_file.name.split('.')[-1].lower()
        
        if file_extension not in allowed_extensions:
            return JsonResponse({
                "status": "error", 
                "message": f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
            }, status=400)
        
        # Create VideoMetadata instance
        video_metadata = VideoMetadata.objects.create(
            chapter=chapter,
            course=chapter.course,
            video_type='upload',
            title=title,
            description=description,
            video_file=video_file,
            relevance_point="Main Content"
        )
        
        logger.info(f"Successfully uploaded video: {video_metadata.title}")
        
        return JsonResponse({
            "status": "success",
            "video_id": video_metadata.id,
            "video_url": video_metadata.get_video_url(),
            "embed_url": video_metadata.get_embed_url(),
            "title": video_metadata.title,
            "description": video_metadata.description,
            "is_available": video_metadata.is_video_available(),
            "message": "Video uploaded successfully!"
        })
        
    except Exception as e:
        logger.error(f"Error uploading video: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@require_http_methods(["POST"])
@csrf_exempt
def add_youtube_video_to_chapter(request, chapter_id):
    """Add YouTube video to a specific chapter"""
    try:
        chapter = get_object_or_404(Chapter, id=chapter_id)
        logger.info(f"Processing YouTube video request for chapter {chapter_id}")
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST
            
        video_url = data.get('url', '').strip()
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        
        if not video_url:
            return JsonResponse({"status": "error", "message": "No URL provided"}, status=400)
        
        # Create VideoMetadata instance first to test URL parsing
        video_metadata = VideoMetadata(
            chapter=chapter,
            course=chapter.course,
            video_type='youtube',
            youtube_url=video_url,
        )
        
        # Test if we can extract YouTube ID
        youtube_id = video_metadata.youtube_id
        if not youtube_id:
            return JsonResponse({
                "status": "error", 
                "message": "Invalid YouTube URL. Please provide a valid YouTube video URL."
            }, status=400)
        
        # If title/description not provided, try to fetch from YouTube
        if not title or not description:
            try:
                from .ai_integration.youtube_fetcher import fetch_youtube_videos
                from .ai_integration.ai_module import summarize_video
                
                video_data = fetch_youtube_videos(video_url, max_results=1)[0]
                title = title or video_data.get("title", "YouTube Video")
                description = description or video_data.get("description", "")
                if not description:
                    description = summarize_video(title, video_data.get("description", ""))
            except Exception as e:
                logger.warning(f"Could not fetch YouTube data: {e}")
                title = title or "YouTube Video"
                description = description or "YouTube video description"
        
        # Now save with all the data
        video_metadata.title = title
        video_metadata.description = description
        video_metadata.relevance_point = "Main Content"
        video_metadata.save()
        
        logger.info(f"Successfully added YouTube video: {video_metadata.title}")
        
        return JsonResponse({
            "status": "success",
            "video_id": video_metadata.id,
            "embed_url": video_metadata.get_embed_url(),
            "youtube_id": video_metadata.get_youtube_id(),
            "title": video_metadata.title,
            "description": video_metadata.description,
            "is_available": video_metadata.is_video_available(),
            "message": "YouTube video added successfully!"
        })
        
    except Exception as e:
        logger.error(f"Error adding YouTube video: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

# Add this debugging view to help troubleshoot
def debug_video_status(request, course_id):
    """Debug view to check video status - remove in production"""
    course = get_object_or_404(Course, id=course_id)
    videos = VideoMetadata.objects.filter(course=course)
    
    debug_info = []
    for video in videos:
        info = {
            'id': video.id,
            'title': video.title,
            'type': video.video_type,
            'is_available': video.is_video_available(),
        }
        
        if video.video_type == 'youtube':
            info.update({
                'youtube_url': video.youtube_url,
                'youtube_id': video.youtube_id,
                'embed_url': video.embed_url,
            })
        else:
            info.update({
                'video_file': str(video.video_file) if video.video_file else None,
                'upload_url': video.upload_url,
                'file_exists': bool(video.video_file and video.video_file.name),
            })
        
        debug_info.append(info)
    
    return JsonResponse({'videos': debug_info})

@require_http_methods(["POST"])
@csrf_exempt
def upload_video(request, draft_id):
    """Handle video file uploads for draft (existing functionality)"""
    try:
        logger.info(f"Processing video upload for draft {draft_id}")
        
        if not request.FILES.get('video'):
            return JsonResponse({"status": "error", "message": "No video file provided"}, status=400)

        video_file = request.FILES['video']
        file_path = default_storage.save(
            f'course_videos/{draft_id}/{video_file.name}',
            video_file
        )
        
        video_url = default_storage.url(file_path)
        
        logger.info(f"Successfully uploaded video: {file_path}")
        
        return JsonResponse({
            "status": "success",
            "video_url": video_url,
            "file_name": video_file.name
        })
    except Exception as e:
        logger.error(f"Error uploading video: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)



@require_http_methods(["POST"])
@csrf_exempt
def add_youtube_video(request):
    """Process and add YouTube video to course content (existing functionality)"""
    try:
        logger.info("Processing YouTube video request")
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST
            
        video_url = data.get('url')
        
        if not video_url:
            return JsonResponse({"status": "error", "message": "No URL provided"}, status=400)
            
        video_data = fetch_youtube_videos(video_url, max_results=1)[0]
        summary = summarize_video(video_data["title"], video_data["description"])
        
        logger.info(f"Successfully processed YouTube video: {video_data['title']}")
        
        return JsonResponse({
            "status": "success",
            "video_data": video_data,
            "summary": summary
        })
    except Exception as e:
        logger.error(f"Error adding YouTube video: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

@require_http_methods(["DELETE"])
@csrf_exempt
def delete_video(request, video_id):
    """Delete a video from a chapter"""
    try:
        video = get_object_or_404(VideoMetadata, id=video_id)
        
        # Delete the file if it's an uploaded video
        if video.video_type == 'upload' and video.video_file:
            try:
                default_storage.delete(video.video_file.name)
            except Exception as e:
                logger.warning(f"Could not delete video file: {e}")
        
        video.delete()
        
        return JsonResponse({
            "status": "success",
            "message": "Video deleted successfully!"
        })
        
    except Exception as e:
        logger.error(f"Error deleting video: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
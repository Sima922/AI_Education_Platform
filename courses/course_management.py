from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import Http404
from django.forms import formset_factory
from urllib.parse import urlparse
import os
from django.utils import timezone
from django.urls import reverse
from django.http import JsonResponse
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from django.utils.timezone import now
from django.contrib.auth.decorators import login_required
from django.conf import settings
from datetime import timedelta
from .models import Enrollment, Chapter
from django.core.files.storage import default_storage
import logging
import json
from .models import CourseExam
from .models import Course, Topic, Chapter, VideoMetadata, CourseExam, ExamQuestion, ExamSession, UserProgress
from .forms import ExamConfigurationForm
from .models import Course, Topic, Chapter, CourseDraft, CourseVersion
from .models import Course, Topic, Chapter, Enrollment, VideoMetadata, CourseDraft, User
from django.views.decorators.csrf import csrf_protect
from django.db.models import Count
from django.views.decorators.csrf import csrf_exempt
from .forms import CourseForm, TopicForm, ChapterForm
from courses.ai_integration.preprocessing import organize_inputs
from .utils import get_smart_course_recommendations, get_trending_courses, get_quality_new_courses
from .ai_integration.ai_module import fix_course_typos
from .ai_integration.ai_module import (
    generate_chapter_content,
    generate_quiz,
    generate_video_search_query,
    summarize_video,
    generate_practical_examples,
    generate_learning_objectives,
    fix_course_typos,
    generate_course_from_prompt,
    generate_comprehensive_exam,
)
from .ai_integration.youtube_fetcher import fetch_youtube_videos

logger = logging.getLogger(__name__)

def homepage(request):
    """
    Updated homepage with advanced recommendation algorithms
    """
    # 1. Smart trending courses using advanced algorithm
    trending_courses = get_trending_courses(limit=8)
    
    # 2. Quality new courses with filtering
    new_courses = get_quality_new_courses(limit=8)
    
    # 3. Smart personalized recommendations
    recommended_courses = get_smart_course_recommendations(request.user, limit=8)
    
    # 4. Safe enrolled-courses lookup (keep existing logic)
    enrolled_courses = []
    if request.user.is_authenticated:
        try:
            enrolled_courses = (
                Enrollment.objects
                          .filter(user=request.user)
                          .select_related("course")
            )
        except (ValueError, TypeError):
            enrolled_courses = []
    
    # 5. Additional context for frontend
    context = {
        "trending_courses": trending_courses,
        "new_courses": new_courses,
        "recommended_courses": recommended_courses,
        "enrolled_courses": enrolled_courses,
        # Add metadata for frontend
        "has_personalized_recs": request.user.is_authenticated,
        "total_courses": Course.objects.count(),
        "user_enrollment_count": len(enrolled_courses) if enrolled_courses else 0,
    }
    
    return render(request, "homepage.html", context)

@require_http_methods(["GET"])
def get_course_recommendations(request):
    """
    API endpoint for getting course recommendations
    Useful for infinite scroll or refreshing recommendations
    """
    recommendation_type = request.GET.get('type', 'recommended')
    limit = int(request.GET.get('limit', 8))
    
    if recommendation_type == 'trending':
        courses = get_trending_courses(limit)
    elif recommendation_type == 'new':
        courses = get_quality_new_courses(limit)
    else:
        courses = get_smart_course_recommendations(request.user, limit)
    
    # Serialize course data
    course_data = []
    for course in courses:
        course_data.append({
            'id': course.id,
            'title': course.title,
            'description': course.description[:200] + '...' if len(course.description) > 200 else course.description,
            'price': float(course.price),
            'thumbnail': course.thumbnail.url if course.thumbnail else None,
            'creator': course.creator.username if course.creator else 'Anonymous',
            'created_at': course.created_at.isoformat(),
            'enrollment_count': getattr(course, 'enrollment_count', 0),
            'trending_score': getattr(course, 'trending_score', 0),
        })
    
    return JsonResponse({
        'courses': course_data,
        'recommendation_type': recommendation_type,
        'count': len(course_data)
    })
    

@login_required
def preview_course(request, draft_id=None):
    """Handle course preview with real-time editing capabilities and file context."""
    logger.info("Accessing course preview page")

    if draft_id:
        draft = get_object_or_404(CourseDraft, id=draft_id)
        if request.user.is_authenticated and draft.creator != request.user:
            messages.error(request, "You don't have permission to preview this draft.")
            return redirect("courses:homepage")
        
        course_data = draft.content
        form_data = draft.form_data
        versions = CourseVersion.objects.filter(draft=draft).order_by('-created_at')
        exam_config = draft.exam_config
        exam_form = None
        if exam_config:
            exam_form = ExamConfigurationForm(initial=exam_config)
        else:
            exam_form = ExamConfigurationForm()
            
        
        logger.debug(f"Preview draft data: {course_data}")
        
        context = {
            "course_data": course_data,
            "draft_id": draft_id,
            "form_data": form_data,
            "versions": versions,
            "draft_thumbnail": draft.thumbnail,
            "exam_form": exam_form,
            
            "can_edit": request.user.is_authenticated and (
                not draft.creator or draft.creator == request.user
            )
        }
        return render(request, "preview_course.html", context)

    # Handle new course preview
    ChapterFormSet = formset_factory(ChapterForm, extra=2)

    if request.method == "POST":
        logger.info("POST request received")
        course_form = CourseForm(request.POST, request.FILES)
        topic_form = TopicForm(request.POST)
        chapter_formset = ChapterFormSet(request.POST, prefix="chapters")

        logger.info(f"Course form valid: {course_form.is_valid()}")
        logger.info(f"Topic form valid: {topic_form.is_valid()}")
        logger.info(f"Chapter formset valid: {chapter_formset.is_valid()}")

        if all([course_form.is_valid(), topic_form.is_valid(), chapter_formset.is_valid()]):
            logger.info("All forms are valid")
            try:
                chapters_data = [
                    form.cleaned_data 
                    for form in chapter_formset 
                    if form.cleaned_data.get("title", "").strip()
                ]

                if not chapters_data:
                    logger.warning("No chapters provided")
                    messages.error(request, "At least one chapter is required.")
                    context = {
                        "course_form": course_form,
                        "topic_form": topic_form,
                        "chapter_formset": chapter_formset,
                    }
                    return render(request, "create_course.html", context)

                # Collect all uploaded files
                course_files = request.FILES.getlist('course_files')
                topic_files = request.FILES.getlist('topic_files')
                chapter_files = []
                for i in range(len(chapters_data)):
                    chapter_files.extend(request.FILES.getlist(f'chapter_files_{i}'))
                
                # Process files and extract context
                
                organized_data = organize_inputs(
                    outline="",
                    chapters=[chap['title'] for chap in chapters_data],
                    documents=[],
                    course_files=course_files,
                    topic_files=topic_files,
                    chapter_files=chapter_files
                )
                
                file_context = organized_data.get('file_context', '')
                keywords = organized_data.get('keywords', [])
                
                course_title = course_form.cleaned_data["title"]
                course_title = fix_course_typos(course_title)
                
                # Form data with file context metadata
                form_data = {
                    "course": {
                        "title": course_form.cleaned_data["title"],
                        "description": course_form.cleaned_data["description"],
                        "file_context": file_context[:1000],  # Store snippet for reference
                        "keywords": keywords
                    },
                    "topic": topic_form.cleaned_data,
                    "chapters": chapters_data,
                }
                
                course_data = {
                    "title": course_title,
                    "description": course_form.cleaned_data["description"],
                    "topic": topic_form.cleaned_data["title"],
                    "chapters": []
                }
                
                # Generate chapter content with file context
                for index, chapter_form in enumerate(chapters_data, 1):
                    chapter_title = chapter_form["title"]
                    topic = topic_form.cleaned_data["title"]
                    
                    chapter_content = generate_chapter_content(
                        chapter_title=chapter_title,
                        course_topic=topic,
                        file_context=file_context,
                        keywords=keywords
                    )
                    
                    learning_objectives = generate_learning_objectives(
                        chapter_title=chapter_title,
                        chapter_content=str(chapter_content),
                        file_context=file_context,
                        keywords=keywords
                    )
                    
                    practical_examples = generate_practical_examples(
                        chapter_title=chapter_title,
                        chapter_content=str(chapter_content),
                        file_context=file_context,
                        keywords=keywords
                    )
                    
                    quiz = generate_quiz(
                        chapter_title=chapter_title,
                        chapter_content=str(chapter_content),
                        file_context=file_context,
                        keywords=keywords
                    )
                    
                    search_query = generate_video_search_query(
                        topic=topic,
                        subtopic=chapter_title,
                        chapter_content=chapter_content,
                        file_context=file_context,
                        keywords=keywords
                    )
                    
                    videos = fetch_youtube_videos(
                        query=search_query, 
                        max_results=8,
                        keywords=keywords or []
                    )
                    
                    video_content = []
                    for video in videos:
                        summary = summarize_video(video["title"], video["description"])
                        video_content.append({
                            "video": video,
                            "summary": summary,
                            "relevance_point": chapter_title
                        })
                    
                    chapter_data = {
                        "number": index,
                        "title": chapter_title,
                        "introduction": chapter_content["introduction"],
                        "learning_objectives": learning_objectives,
                        "main_content": chapter_content["main_content"],
                        "practical_examples": practical_examples,
                        "summary": chapter_content["summary"],
                        "quiz": quiz,
                        "videos": video_content
                    }
                    course_data["chapters"].append(chapter_data)

                # Create draft with thumbnail and file context
                draft = CourseDraft.objects.create(
                    creator=request.user,
                    content=course_data,
                    form_data=form_data,
                    thumbnail=request.FILES.get('thumbnail')
                )
                
                # Create initial version
                CourseVersion.objects.create(
                    draft=draft,
                    content=course_data,
                    version_type='draft',
                    created_by=request.user
                )

                return render(request, "preview_course.html", {
                    "course_data": course_data,
                    "draft_id": draft.id,
                    "form_data": draft.form_data,
                    "draft_thumbnail": draft.thumbnail,
                    "can_edit": True,
                    "keywords": keywords  # Pass keywords to template
                })

            except Exception as e:
                logger.error(f"Error generating course preview: {e}", exc_info=True)
                messages.error(request, f"Error generating preview: {str(e)}")
        else:
            logger.warning("Form validation failed")
            messages.error(request, "Please correct the errors in the form.")
    else:
        logger.info("GET request received")
        course_form = CourseForm()
        topic_form = TopicForm()
        chapter_formset = ChapterFormSet(prefix="chapters")

    context = {
        "course_form": course_form,
        "topic_form": topic_form,
        "chapter_formset": chapter_formset,
    }
    
    return render(request, "create_course.html", context)

@require_http_methods(["POST"])
def save_draft_version(request, draft_id):
    """Save a new version of the course draft."""
    try:
        draft = get_object_or_404(CourseDraft, id=draft_id)
        if request.user.is_authenticated and draft.creator != request.user:
            raise PermissionDenied

        logger.info(f"Saving new draft version for draft_id: {draft_id}")
        
        # Handle both JSON and form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            course_content = data.get('content')
        else:
            course_content = request.POST.get('content')

        if not course_content:
            raise ValueError("No course content provided")
        # Get form data if provided
        form_data = None
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            form_data = data.get('form_data')
                
        # Create new version
        version = CourseVersion.objects.create(
            draft=draft,
            content=course_content,
            version_type='draft',
            created_by=request.user if request.user.is_authenticated else None
        )
        
        # Update draft content
        draft.content = course_content
        if form_data:
            updated_form_data = draft.form_data.copy()
            for key in form_data:
                if isinstance(form_data[key], dict) and key in updated_form_data and isinstance(updated_form_data[key], dict):
                    updated_form_data[key].update(form_data[key])
                else:
                    updated_form_data[key] = form_data[key]
                    
                    draft.form_data = updated_form_data
        draft.save()
        
        logger.info(f"Successfully saved draft version {version.id}")

        return JsonResponse({
            "status": "success",
            "version_id": version.id,
            "timestamp": version.created_at.isoformat()
        })
    except Exception as e:
        logger.error(f"Error saving draft version: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

@require_http_methods(["POST"])
def restore_version(request, version_id):
    """Restore a previous version of the course."""
    try:
        version = get_object_or_404(CourseVersion, id=version_id)
        draft = version.draft
        
        logger.info(f"Attempting to restore version {version_id} for draft {draft.id}")
        
        if request.user.is_authenticated and draft.creator != request.user:
            raise PermissionDenied

        # Update draft content with version content
        draft.content = version.content
        draft.save()
        
        logger.info(f"Successfully restored version {version_id}")

        return JsonResponse({
            "status": "success",
            "content": version.content
        })
    except Exception as e:
        logger.error(f"Error restoring version: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

def create_course_with_prompt(request):
    """Create a course using a natural language prompt"""
    if request.method == 'POST':
        prompt = request.POST.get('prompt', '')
        try:
            # Generate course structure from prompt
            course_structure = generate_course_from_prompt(prompt)
            
            # Create course draft
            draft = CourseDraft.objects.create(
                creator=request.user if request.user.is_authenticated else None,
                content=course_structure,
                form_data={
                    "course": {"title": course_structure['title'], "description": course_structure['description']},
                    "topic": {"title": course_structure['topic']},
                    "chapters": [{"title": ch['title']} for ch in course_structure['chapters']]
                }
            )
            
            # Create initial version
            CourseVersion.objects.create(
                draft=draft,
                content=course_structure,
                version_type='draft',
                created_by=request.user if request.user.is_authenticated else None
            )
            
            return redirect(reverse('courses:preview_course', kwargs={'draft_id': draft.id}))
        
        except Exception as e:
            logger.error(f"Error generating course from prompt: {e}")
            messages.error(request, f"Error generating course: {str(e)}")
            return redirect('courses:create_with_prompt')
    
    return render(request, 'create_with_prompt.html')


@csrf_protect
@transaction.atomic
def create_course(request):
    """Publish the course from preview/draft state with file context."""
    if request.method != "POST":
        messages.error(request, "Invalid request method")
        return redirect("courses:homepage")
        
    draft_id = None
    course = None
    
    try:
        logger.info("Starting course creation process")
        
        # Get draft ID from either POST data or session
        draft_id = request.POST.get('draft_id') or request.session.get("editing_draft_id")
        
        # Handle both JSON and form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            course_data = data.get('content')
            draft_id = data.get('draft_id')
            
            if draft_id:
                draft = get_object_or_404(CourseDraft, id=draft_id)
                form_data = data.get('form_data', draft.form_data)
                exam_config = data.get('exam_config', draft.exam_config)
                # Update draft form_data with the latest changes
                if data.get('form_data'):
                    draft.form_data = data.get('form_data')
                if data.get('exam_config'):
                    draft.exam_config = data.get('exam_config')
                        
                    draft.save()
            else:
                form_data = data.get('form_data')
                exam_config = data.get('exam_config')
        else:
            if draft_id:
                draft = get_object_or_404(CourseDraft, id=draft_id)
                if request.user.is_authenticated and draft.creator != request.user:
                    raise PermissionDenied
                    
                course_data = draft.content
                form_data = draft.form_data
                exam_config = draft.exam_config
            else:
                raise ValueError("No draft ID provided")
        
        if not form_data or not course_data:
            raise ValueError("No course data found")
            
        logger.info("Creating course with data:", extra={
            'form_data': form_data,
            'creator': request.user.username if request.user.is_authenticated else 'anonymous'
        })
        
        # Create the course with file context metadata
        course = Course.objects.create(
            title=form_data["course"]["title"],
            description=form_data["course"]["description"],
            creator=request.user if request.user.is_authenticated else None,
            thumbnail=draft.thumbnail if draft.thumbnail else None,
            file_context=form_data["course"].get("file_context", ""),
            keywords=form_data["course"].get("keywords", [])
        )
        
        logger.info(f"Created course with ID: {course.id}")
        
        # Create the topic
        topic = Topic.objects.create(
            course=course,
            title=form_data["topic"]["title"],
            description=form_data["topic"].get("description", ""),
        )
        
        # Create chapters and content with file context
        for chapter_data in course_data["chapters"]:
            chapter = Chapter.objects.create(
                course=course,
                title=chapter_data["title"],
                introduction=chapter_data["introduction"],
                learning_objectives=chapter_data["learning_objectives"],
                main_content=chapter_data["main_content"],
                practical_examples=chapter_data["practical_examples"],
                summary=chapter_data.get("summary", ""),
                quiz=chapter_data.get("quiz", {"questions": []}),
                order=chapter_data.get("number", 0)
            )
            
            # Create videos
            for video_data in chapter_data.get("videos", []):
                video_info = video_data["video"]
                video_source = video_info.get("source", "")
                video_title = video_info.get("title", "Untitled Video")
                video_description = video_data.get("summary", video_info.get("description", ""))
                relevance_point = video_data.get("relevance_point", "Main Content")
                logger.info(f"Processing video: {video_title}, source: {video_source}")
                try:
                    if (video_info.get("video_type") == "youtube" or
                        "youtube.com" in video_source or
                        "youtu.be" in video_source):
                        VideoMetadata.objects.create(
                            chapter=chapter,
                            course=course,
                            title=video_title,
                            description=video_description,
                            youtube_url=video_source,
                            video_type="youtube",
                            relevance_point=relevance_point
                        )
                        logger.info(f"Created YouTube video: {video_title}")
                    elif video_source:
                        video_file_path = video_source
                        if video_file_path.startswith(('http://', 'https://')):
                            parsed = urlparse(video_file_path)
                            video_file_path = parsed.path
                        if video_file_path.startswith(settings.MEDIA_URL):
                            video_file_path = video_file_path[len(settings.MEDIA_URL):]
                        elif video_file_path.startswith('/media/'):
                            video_file_path = video_file_path[len('/media/'):]
                        video_file_path = video_file_path.lstrip('/')
                        full_file_path = os.path.join(settings.MEDIA_ROOT, video_file_path)
                        if os.path.exists(full_file_path):
                            VideoMetadata.objects.create(
                                chapter=chapter,
                                course=course,
                                title=video_title,
                                description=video_description,
                                video_file=video_file_path,
                                video_type="upload",
                                relevance_point=relevance_point
                            )
                            logger.info(f"Created uploaded video: {video_title} at {video_file_path}")
                        else:
                            logger.warning(f"Video file not found: {full_file_path}")
                            VideoMetadata.objects.create(
                                chapter=chapter,
                                course=course,
                                title=video_title,
                                description=video_description,
                                video_file=video_file_path,
                                video_type="upload",
                            )
                            logger.warning(f"Created video entry with missing file: {video_title}")
                    else:
                        logger.warning(f"No valid video source found for: {video_title}")
                except Exception as e:
                    logger.error(f"Error creating video {video_title}: {e}", exc_info=True)
                    continue
        if exam_config and exam_config.get('enable_exam'):
            try:
                exam = CourseExam.objects.create(
                    course=course,
                    exam_type=exam_config.get('exam_type', 'default'),
                    prompt=exam_config.get('prompt', ''),
                    time_limit_minutes=exam_config.get('time_limit_minutes', 120),
                    passing_score=exam_config.get('passing_score', 70.0),
                    max_attempts=exam_config.get('max_attempts', 1),
                    is_enabled=True
                    )
                exam_structure = generate_comprehensive_exam(
                    course_content=course_data,
                    prompt=exam.prompt,
                    template_file=None  # Would need file handling for templates
                    )
                exam.structure = exam_structure
                exam.save()
                # Create exam questions
                for i, question_data in enumerate(exam_structure.get('questions', [])):
                    ExamQuestion.objects.create(
                        exam=exam,
                        question_type=question_data['type'],
                        question_text=question_data['question'],
                        options=question_data.get('options'),
                        correct_answer=question_data.get('correct_answer'),
                        points=question_data.get('points', 1),
                        order=i
                         )
                logger.info(f"Created exam for course {course.id}")
            except Exception as e:
                logger.error(f"Error creating exam: {e}")
                messages.warning(request, "Course created successfully, but there was an error creating the exam")
                    
                            
        
        # Create final published version if from draft
        if draft_id:
            CourseVersion.objects.create(
                draft=draft,
                content=course_data,
                version_type='published',
                created_by=request.user if request.user.is_authenticated else None
            )
            
            # Only delete draft after confirming course creation
            draft.delete()
            logger.info(f"Deleted draft {draft_id} after successful course creation")
        
        # Cleanup session
        if 'editing_draft_id' in request.session:
            del request.session['editing_draft_id']
        
        messages.success(request, "Course published successfully!")
        
        if request.content_type == 'application/json':
            return JsonResponse({
                "status": "success",
                "course_id": course.id,
                "redirect_url": reverse("courses:view_course", kwargs={"pk": course.id})
            })
        return redirect(reverse("courses:view_course", kwargs={"pk": course.id}))
            
    except Exception as e:
        logger.error(f"Error creating course: {e}", exc_info=True, extra={
            'draft_id': draft_id,
            'course_id': course.id if course else None
        })
        
        # Rollback any partial course creation
        if course:
            try:
                course.delete()
                logger.info(f"Rolled back course creation for course {course.id}")
            except Exception as delete_error:
                logger.error(f"Error rolling back course creation: {delete_error}", exc_info=True)
        
        messages.error(request, f"Error publishing course: {str(e)}")
        if request.content_type == 'application/json':
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
        return redirect("courses:homepage")
    
def debug_course_videos(request, course_id):
    """Debug view to check video data - add this to your views.py"""
    course = get_object_or_404(Course, id=course_id)
    videos = VideoMetadata.objects.filter(course=course)
    
    debug_info = []
    for video in videos:
        debug_info.append({
            'id': video.id,
            'title': video.title,
            'video_type': video.video_type,
            'video_file': str(video.video_file) if video.video_file else None,
            'video_file_exists': os.path.exists(os.path.join(settings.MEDIA_ROOT, str(video.video_file))) if video.video_file else False,
            'get_video_url': video.get_video_url(),
            'get_embed_url': video.get_embed_url(),
            'youtube_url': video.youtube_url,
        })
    
    return JsonResponse({'videos': debug_info})

def debug_video_paths(request, course_id):
    """Debug view to check video paths and files"""
    if not settings.DEBUG:
        return JsonResponse({"error": "Debug mode only"}, status=403)
        
    course = get_object_or_404(Course, id=course_id)
    videos = VideoMetadata.objects.filter(course=course)
    
    debug_info = []
    for video in videos:
        video_info = {
            'id': video.id,
            'title': video.title,
            'video_type': video.video_type,
            'video_file_field': str(video.video_file) if video.video_file else None,
            'get_video_url': video.get_video_url(),
            'get_embed_url': video.get_embed_url(),
            'youtube_url': video.youtube_url,
        }
        
        if video.video_type == 'upload' and video.video_file:
            file_path = os.path.join(settings.MEDIA_ROOT, str(video.video_file))
            video_info['file_exists'] = os.path.exists(file_path)
            video_info['file_path'] = file_path
            video_info['file_size'] = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            
        debug_info.append(video_info)
    
    return JsonResponse({'videos': debug_info}, indent=2)   

@require_http_methods(["POST"])
def update_course_content(request, draft_id):
    """Handle real-time updates to course content."""
    try:
        draft = get_object_or_404(CourseDraft, id=draft_id)
        if request.user.is_authenticated and draft.creator != request.user:
            raise PermissionDenied

        data = json.loads(request.body)
        section = data.get('section')
        content = data.get('content')
        chapter_index = data.get('chapter_index')
        
        if not all([section, content]):
            return JsonResponse({
                "status": "error",
                "message": "Missing required fields"
            }, status=400)

        course_data = draft.content
        
        # Update specific section
        if chapter_index is not None:
            if 0 <= chapter_index < len(course_data["chapters"]):
                chapter = course_data["chapters"][chapter_index]
                if section in chapter:
                    chapter[section] = content
                else:
                    return JsonResponse({
                        "status": "error",
                        "message": f"Invalid section: {section}"
                    }, status=400)
            else:
                return JsonResponse({
                    "status": "error",
                    "message": "Invalid chapter index"
                }, status=400)
        else:
            if section in course_data:
                course_data[section] = content
            else:
                return JsonResponse({
                    "status": "error",
                    "message": f"Invalid section: {section}"
                }, status=400)

        # Save updates
        draft.content = course_data
        draft.save()
        
        # Create auto-save version
        CourseVersion.objects.create(
            draft=draft,
            content=course_data,
            version_type='auto-save',
            created_by=request.user if request.user.is_authenticated else None
        )

        return JsonResponse({"status": "success"})
        
    except Exception as e:
        logger.error(f"Error updating course content: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

@require_http_methods(["POST"])
def reorder_chapters(request, draft_id):
    """Handle chapter reordering."""
    try:
        draft = get_object_or_404(CourseDraft, id=draft_id)
        if request.user.is_authenticated and draft.creator != request.user:
            raise PermissionDenied

        data = json.loads(request.body)
        new_order = data.get('chapter_order', [])
        
        if not new_order:
            return JsonResponse({
                "status": "error",
                "message": "No chapter order provided"
            }, status=400)

        course_data = draft.content
        chapters = course_data["chapters"]
        
        # Create new ordered list of chapters
        ordered_chapters = []
        for index in new_order:
            if 0 <= index < len(chapters):
                chapter = chapters[index].copy()
                chapter["number"] = len(ordered_chapters) + 1
                ordered_chapters.append(chapter)

        course_data["chapters"] = ordered_chapters
        draft.content = course_data
        draft.save()

        # Create version for chapter reorder
        CourseVersion.objects.create(
            draft=draft,
            content=course_data,
            version_type='draft',
            created_by=request.user if request.user.is_authenticated else None
        )

        return JsonResponse({"status": "success"})
        
    except Exception as e:
        logger.error(f"Error reordering chapters: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

@require_http_methods(["POST"])
def delete_chapter(request, draft_id):
    """Handle chapter deletion."""
    try:
        draft = get_object_or_404(CourseDraft, id=draft_id)
        if request.user.is_authenticated and draft.creator != request.user:
            raise PermissionDenied

        data = json.loads(request.body)
        chapter_index = data.get('chapter_index')
        
        if chapter_index is None:
            return JsonResponse({
                "status": "error",
                "message": "No chapter index provided"
            }, status=400)

        course_data = draft.content
        chapters = course_data["chapters"]
        
        if 0 <= chapter_index < len(chapters):
            # Remove chapter
            deleted_chapter = chapters.pop(chapter_index)
            
            # Renumber remaining chapters
            for i, chapter in enumerate(chapters, 1):
                chapter["number"] = i
            
            draft.content = course_data
            draft.save()

            # Create version for chapter deletion
            CourseVersion.objects.create(
                draft=draft,
                content=course_data,
                version_type='draft',
                created_by=request.user if request.user.is_authenticated else None
            )

            return JsonResponse({
                "status": "success",
                "deleted_chapter": deleted_chapter["title"]
            })
        else:
            return JsonResponse({
                "status": "error",
                "message": "Invalid chapter index"
            }, status=400)
            
    except Exception as e:
        logger.error(f"Error deleting chapter: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
        
@login_required    
def view_course(request, pk):
    """View a published course with automatic enrollment."""
    try:
        logger.info(f"Accessing course view for course ID: {pk}")
        
        course = get_object_or_404(Course, pk=pk)
        
        # Check if user is authenticated
        if not request.user.is_authenticated:
            messages.info(request, "Please log in to access this course.")
            return redirect('courses:login')
        
        # Check if user is already enrolled
        enrollment = Enrollment.objects.filter(user=request.user, course=course).first()
        
        # Auto-enroll user if not already enrolled and course is free
        if not enrollment:
            if course.price == 0:  # Free course
                try:
                    with transaction.atomic():
                        enrollment = Enrollment.objects.create(
                            user=request.user, 
                            course=course
                        )
                        messages.success(request, f"You've been enrolled in '{course.title}'!")
                        logger.info(f"User {request.user.id} auto-enrolled in course {course.id}")
                except Exception as e:
                    logger.error(f"Error auto-enrolling user {request.user.id} in course {course.id}: {e}")
                    messages.error(request, "Error enrolling in course. Please try again.")
                    return redirect('courses:homepage')
            else:
                # Paid course - redirect to enrollment page or payment
                messages.info(request, f"This course costs ${course.price}. Please complete enrollment.")
                return redirect('courses:enroll_course', course_id=course.id)
        
        # Get chapters with related data
        chapters = (
            course.chapter_set.all()
            .prefetch_related('videometadata_set')
            .order_by('order')
        )
        
        # Calculate progress if user is enrolled
        progress = 0
        if enrollment:
            # Simple progress calculation - you can make this more sophisticated
            total_chapters = chapters.count()
            if total_chapters > 0:
                # For now, just set progress to 0 - you can implement actual progress tracking
                progress = 0
        # Check exam status
        exam = None
        exam_status = None
        exam_attempts = 0
        certificate_earned = enrollment.certificate_earned
        
        if hasattr(course, 'exam') and course.exam.is_enabled:
            exam = course.exam
            exam_attempts = ExamSession.objects.filter(
                user=request.user,
                exam=exam
                ).count()
             # Check if user has completed the course
            completed_chapters = UserProgress.objects.filter(
                user=request.user,
                course=course,
                chapter_completed=True
                ).count()
            exam_status = {
                'has_exam': True,
                'is_eligible': completed_chapters >= chapters.count(),
                'attempts_remaining': max(0, exam.max_attempts - exam_attempts),
                'certificate_earned': certificate_earned
                 }
                     
        
        context = {
            "course": course,
            "chapters": chapters,
            "progress": progress,
            "can_edit": course.creator == request.user,
            "is_enrolled": enrollment is not None,
            "enrollment": enrollment,
            "exam": exam,
            "exam_status": exam_status,
            
        }
        
        logger.info(f"Successfully rendered course view for course {pk}")
        
        return render(request, "courses/view_course.html", context)
        
    except Exception as e:
        logger.error(f"Error viewing course {pk}: {e}", exc_info=True)
        messages.error(request, "Error loading course")
        return redirect("courses:homepage")
  
@login_required
def track_progress(request, chapter_id):
    # Dummy response for now; implement actual progress tracking logic here
    return JsonResponse({'message': f"Tracking progress for chapter {chapter_id}"})


@login_required
def edit_course(request, course_id):
    """
    View to edit an existing course
    """
    try:
        course = get_object_or_404(Course, id=course_id)
        
        # Check if user has permission to edit this course
        if course.created_by != request.user:
            messages.error(request, "You don't have permission to edit this course.")
            return redirect('courses:view_course', pk=course_id)
        
        if request.method == 'POST':
            # Handle form submission to update course
            title = request.POST.get('title')
            description = request.POST.get('description')
            
            if title and description:
                course.title = title
                course.description = description
                course.save()
                
                messages.success(request, "Course updated successfully!")
                return redirect('courses:view_course', pk=course_id)
            else:
                messages.error(request, "Please fill in all required fields.")
        
        context = {
            'course': course,
        }
        
        return render(request, 'courses/edit_course.html', context)
        
    except Course.DoesNotExist:
        raise Http404("Course not found")
    except Exception as e:
        messages.error(request, f"Error editing course: {str(e)}")
        return redirect('courses:course_list')

@login_required
def delete_course(request, course_id):
    """
    View to delete an existing course
    """
    try:
        course = get_object_or_404(Course, id=course_id)
        
        # Check if user has permission to delete this course
        if course.created_by != request.user:
            messages.error(request, "You don't have permission to delete this course.")
            return redirect('courses:view_course', pk=course_id)
        
        if request.method == 'POST':
            course_title = course.title
            course.delete()
            messages.success(request, f"Course '{course_title}' has been deleted successfully!")
            return redirect('courses:course_list')
        
        # If not POST, redirect back to course view
        return redirect('courses:view_course', pk=course_id)
        
    except Course.DoesNotExist:
        raise Http404("Course not found")
    except Exception as e:
        messages.error(request, f"Error deleting course: {str(e)}")
        return redirect('courses:course_list')
import logging
import json
from django.conf import settings
from django.db import transaction
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.utils.timezone import now
from django.contrib import messages
from .models import UserProgress, Chapter, Course
from django.forms import formset_factory
from django.utils import timezone
from django.urls import reverse
from courses.models import CourseVersion
from django.http import JsonResponse
from .utils import get_smart_course_recommendations, get_trending_courses, get_quality_new_courses
from django.db.models import Q, Count
from django.views.decorators.http import require_GET
import re
from difflib import SequenceMatcher
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Course, Topic, Chapter, Enrollment, VideoMetadata, CourseDraft, User
from .forms import CourseForm, TopicForm, ChapterForm, VideoForm
from django.views.decorators.csrf import csrf_exempt
from .models import ChatbotConversation, ChatMessage
from .models import CourseExam, ExamSession
from .ai_integration.rag_service import rag_query
from .serializers import (
    CourseSerializer,
    ChapterSerializer,
    EnrollmentSerializer,
    UserSerializer,
)

# Set up logging
logger = logging.getLogger(__name__)

class CourseListCreateView(generics.ListCreateAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = []  # Allow anonymous access

    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            serializer.save(creator=self.request.user)
        else:
            serializer.save(creator=None)

class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = []  # Allow anonymous access

@login_required
@require_POST
def enroll_in_course(request, course_id):
    """Handle course enrollment."""
    try:
        course = get_object_or_404(Course, id=course_id)
        
        # Check if already enrolled
        if Enrollment.objects.filter(user=request.user, course=course).exists():
            messages.info(request, "You are already enrolled in this course.")
            return redirect('courses:view_course', pk=course.id)
        
        # Handle free courses
        if course.price == 0:
            with transaction.atomic():
                enrollment = Enrollment.objects.create(
                    user=request.user,
                    course=course
                )
                messages.success(request, f"Successfully enrolled in '{course.title}'!")
                logger.info(f"User {request.user.id} enrolled in course {course.id}")
                return redirect('courses:view_course', pk=course.id)
        
        # Handle paid courses
        else:
            messages.info(request, f"This course costs ${course.price}. Payment integration needed.")
            # TODO: Implement payment processing here
            return redirect('courses:view_course', pk=course.id)
            
    except Exception as e:
        logger.error(f"Error enrolling user {request.user.id} in course {course_id}: {e}")
        messages.error(request, "Error enrolling in course. Please try again.")
        return redirect('courses:homepage')

# Alternative class-based view (if you prefer to keep the class-based approach)
class EnrollInCourseView(APIView):
    permission_classes = []  # We'll handle auth in the view

    def post(self, request, course_id):
        course = get_object_or_404(Course, id=course_id)

        # Require login
        if not request.user.is_authenticated:
            return Response({"message": "You must be logged in to enroll in a course."}, status=status.HTTP_401_UNAUTHORIZED)

        # Check if already enrolled
        if Enrollment.objects.filter(user=request.user, course=course).exists():
            return Response({"message": "Already enrolled"}, status=status.HTTP_200_OK)

        # Handle free courses
        if course.price == 0:
            try:
                with transaction.atomic():
                    enrollment = Enrollment.objects.create(user=request.user, course=course)
                    serializer = EnrollmentSerializer(enrollment)
                    return Response({
                        "message": "Successfully enrolled",
                        "enrollment": serializer.data
                    }, status=status.HTTP_201_CREATED)
            except Exception as e:
                logger.error(f"Error enrolling user {request.user.id} in course {course_id}: {e}")
                return Response({"message": "Error enrolling in course"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Handle paid courses
        else:
            return Response({
                "message": f"This course costs ${course.price}. Payment required.",
                "course_price": course.price
            }, status=status.HTTP_402_PAYMENT_REQUIRED)

class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = []  # Allow anonymous access

    def get_object(self):
        if self.request.user.is_authenticated:
            return self.request.user
        return None

@require_GET
def smart_search(request):
    """Robust smart search that always returns relevant results"""
    try:
        query = request.GET.get('q', '').strip()
        
        if not query:
            # Return trending courses if no query
            courses = get_trending_courses(limit=12)
            return JsonResponse({
                'courses': [serialize_course(course) for course in courses],
                'search_type': 'trending',
                'message': 'Showing trending courses'
            })
        
        # Get all courses for smart matching
        all_courses = Course.objects.select_related('creator').all()
        
        if not all_courses.exists():
            return JsonResponse({
                'courses': [],
                'search_type': 'empty',
                'message': 'No courses available yet'
            })
        
        # Smart matching algorithm
        results = perform_smart_search(query, all_courses)
        
        # If no results found, return popular courses
        if not results:
            results = get_trending_courses(limit=12)
            search_type = 'fallback'
            message = f'No matches for "{query}". Here are popular courses instead.'
        else:
            search_type = 'smart'
            message = f'Found {len(results)} results for "{query}"'
        
        return JsonResponse({
            'courses': [serialize_course(course) for course in results],
            'search_type': search_type,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Smart search error: {e}", exc_info=True)
        # Return fallback results even on error
        try:
            fallback_courses = get_trending_courses(limit=12)
            return JsonResponse({
                'courses': [serialize_course(course) for course in fallback_courses],
                'search_type': 'error_fallback',
                'message': 'Search encountered an issue. Showing popular courses.'
            })
        except Exception as fallback_error:
            logger.error(f"Fallback search error: {fallback_error}", exc_info=True)
            return JsonResponse({
                'courses': [],
                'search_type': 'error',
                'message': 'Search is temporarily unavailable. Please try again.'
            })

def perform_smart_search(query, courses):
    """Perform intelligent search with multiple matching strategies"""
    query_lower = query.lower()
    query_words = query_lower.split()
    
    # Different matching strategies with scores
    exact_matches = []
    title_matches = []
    description_matches = []
    word_matches = []
    fuzzy_matches = []
    
    for course in courses:
        title_lower = course.title.lower()
        desc_lower = (course.description or "").lower()
        
        # 1. Exact phrase match (highest priority)
        if query_lower in title_lower:
            exact_matches.append((course, 100))
        elif query_lower in desc_lower:
            exact_matches.append((course, 90))
        
        # 2. Title word matches
        elif any(word in title_lower for word in query_words):
            word_count = sum(1 for word in query_words if word in title_lower)
            score = 80 + (word_count * 5)
            title_matches.append((course, score))
        
        # 3. Description word matches
        elif any(word in desc_lower for word in query_words):
            word_count = sum(1 for word in query_words if word in desc_lower)
            score = 60 + (word_count * 3)
            description_matches.append((course, score))
        
        # 4. Partial word matches
        else:
            partial_score = 0
            for word in query_words:
                if len(word) > 2:  # Only check words longer than 2 characters
                    # Check title words
                    for title_word in title_lower.split():
                        if word in title_word or title_word in word:
                            partial_score += 30
                    # Check description words
                    for desc_word in desc_lower.split():
                        if word in desc_word or desc_word in word:
                            partial_score += 20
            
            if partial_score > 0:
                word_matches.append((course, partial_score))
        
        # 5. Fuzzy matching (character similarity)
        title_similarity = calculate_similarity(query_lower, title_lower)
        desc_similarity = calculate_similarity(query_lower, desc_lower)
        
        # Lowered thresholds to catch more matches
        if title_similarity > 0.3 or desc_similarity > 0.2:
            fuzzy_score = max(title_similarity, desc_similarity) * 40
            fuzzy_matches.append((course, fuzzy_score))
    
    # Sort each category by score
    exact_matches.sort(key=lambda x: x[1], reverse=True)
    title_matches.sort(key=lambda x: x[1], reverse=True)
    description_matches.sort(key=lambda x: x[1], reverse=True)
    word_matches.sort(key=lambda x: x[1], reverse=True)
    fuzzy_matches.sort(key=lambda x: x[1], reverse=True)
    
    # Combine results
    final_results = []
    seen_courses = set()
    
    # Add results from each category in order of priority
    for category in [exact_matches, title_matches, description_matches, word_matches, fuzzy_matches]:
        for course, score in category:
            if course.id not in seen_courses:
                final_results.append(course)
                seen_courses.add(course.id)
            
            # Limit to 12 results
            if len(final_results) >= 12:
                break
        
        if len(final_results) >= 12:
            break
    
    return final_results


def calculate_similarity(text1, text2):
    """Calculate similarity between two strings using SequenceMatcher"""
    try:
        return SequenceMatcher(None, text1, text2).ratio()
    except:
        return 0

def get_trending_courses(limit=12):
    """Get trending courses as fallback"""
    try:
        # Get courses with most enrollments
        trending = Course.objects.annotate(
            enrollment_count=Count('enrollments')
        ).order_by('-enrollment_count', '-created_at')[:limit]
        
        # If no enrollments, get newest courses
        if not trending.exists():
            trending = Course.objects.order_by('-created_at')[:limit]
        
        return list(trending)
    except Exception as e:
        logger.error(f"Error getting trending courses: {e}")
        return []

def serialize_course(course):
    """Serialize course data for JSON response"""
    try:
        return {
            'id': course.id,
            'title': course.title,
            'description': course.description[:150] + '...' if len(course.description or '') > 150 else (course.description or ''),
            'thumbnail_url': course.thumbnail.url if course.thumbnail else None,
            'creator': course.creator.username if course.creator else 'Anonymous',
            'created_at': course.created_at.isoformat(),
            'view_url': reverse('courses:view_course', args=[course.id])
        }
    except Exception as e:
        logger.error(f"Error serializing course {course.id}: {e}")
        return {
            'id': course.id,
            'title': course.title,
            'description': 'Description unavailable',
            'thumbnail_url': None,
            'creator': 'Unknown',
            'created_at': '',
            'view_url': reverse('view_course', args=[course.id])  # ✅ Still use reverse here
        }


@csrf_exempt
@require_POST
def track_section_progress(request):
    """Track when user reads a section"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Not authenticated'})
    
    try:
        data = json.loads(request.body)
        chapter_id = data.get('chapter_id')
        section_type = data.get('section_type')  # 'intro', 'objectives', 'content'
        
        chapter = Chapter.objects.get(id=chapter_id)
        progress, created = UserProgress.objects.get_or_create(
            user=request.user,
            course=chapter.course,
            chapter=chapter
        )
        
        progress.mark_section_read(section_type)
        
        return JsonResponse({
            'success': True,
            'completion_percentage': progress.calculate_completion_percentage()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_POST
def track_video_progress(request):
    """Track when user watches a video"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Not authenticated'})
    
    try:
        data = json.loads(request.body)
        chapter_id = data.get('chapter_id')
        video_id = data.get('video_id')
        
        chapter = Chapter.objects.get(id=chapter_id)
        progress, created = UserProgress.objects.get_or_create(
            user=request.user,
            course=chapter.course,
            chapter=chapter
        )
        
        progress.mark_video_watched(video_id)
        
        return JsonResponse({
            'success': True,
            'completion_percentage': progress.calculate_completion_percentage()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def get_user_progress(request, course_id):
    """Get user's progress for a course"""
    if not request.user.is_authenticated:
        return JsonResponse({'progress': 0})
    
    try:
        course = Course.objects.get(id=course_id)
        chapters = course.chapter_set.all()
        
        total_chapters = chapters.count()
        if total_chapters == 0:
            return JsonResponse({'progress': 0})
        
        # Get user progress for all chapters
        user_progress = UserProgress.objects.filter(
            user=request.user,
            course=course
        )
        
        total_completion = 0
        for chapter in chapters:
            progress = user_progress.filter(chapter=chapter).first()
            if progress:
                total_completion += progress.calculate_completion_percentage()
        
        overall_progress = total_completion / total_chapters if total_chapters > 0 else 0
        
        return JsonResponse({
            'progress': round(overall_progress, 1),
            'chapters_completed': user_progress.filter(chapter_completed=True).count(),
            'total_chapters': total_chapters
        })
    except Exception as e:
        return JsonResponse({'progress': 0, 'error': str(e)})














    


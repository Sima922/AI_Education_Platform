from django.db.models import Count, Q, Avg, F, Value, Case, When, FloatField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.db.models import ExpressionWrapper, DurationField
from django.db.models.functions import Now
from django.contrib.auth.models import AnonymousUser
from datetime import timedelta
import random
import math
from collections import defaultdict
from typing import List, Dict, Tuple, Optional
from .models import Course, Enrollment, User, ChatMessage, ChatbotConversation

class AdvancedRecommendationEngine:
    """
    Advanced recommendation engine with multiple algorithms:
    1. Trending Algorithm: Time-decay weighted popularity
    2. Collaborative Filtering: User-based recommendations
    3. Content-Based Filtering: Course similarity
    4. Hybrid Approach: Combined scoring
    """
    
    def __init__(self, user=None):
        self.user = user if user and user.is_authenticated else None
        self.current_time = timezone.now()
        
    def get_trending_courses(self, limit=8) -> List[Course]:
        """
        Advanced trending algorithm considering:
        - Recent enrollment velocity
        - Time decay factor
        - Engagement metrics
        - Course age normalization
        """
        # Time periods for different weights
        now = self.current_time
        last_day = now - timedelta(days=1)
        last_week = now - timedelta(days=7)
        last_month = now - timedelta(days=30)
        
        courses = Course.objects.annotate(
            # Recent enrollment counts with time decay
            enrollments_last_day=Count(
                'enrollments',
                filter=Q(enrollments__enrolled_at__gte=last_day)
            ),
            enrollments_last_week=Count(
                'enrollments',
                filter=Q(enrollments__enrolled_at__gte=last_week)
            ),
            enrollments_last_month=Count(
                'enrollments',
                filter=Q(enrollments__enrolled_at__gte=last_month)
            ),
            total_enrollments=Count('enrollments'),
            
            # Course age in days
            course_age_days=ExpressionWrapper(
                (Now() - F('created_at')) / timedelta(days=1),
                output_field=FloatField()
                ),
            
            
            # Engagement metrics
            chat_interactions=Count(
                'chatbotconversation__messages',
                filter=Q(chatbotconversation__messages__timestamp__gte=last_week)
            ),
            
            # Calculate trending score
            trending_score=Case(
                When(
                    total_enrollments=0,
                    then=Value(0.0)
                ),
                default=(
                    # Recent activity boost (higher weight for recent enrollments)
                    F('enrollments_last_day') * 10.0 +
                    F('enrollments_last_week') * 5.0 +
                    F('enrollments_last_month') * 2.0 +
                    
                    # Base popularity
                    F('total_enrollments') * 1.0 +
                    
                    # Engagement boost
                    F('chat_interactions') * 0.5 +
                    
                    # Age normalization (newer courses get slight boost)
                    Case(
                        When(course_age_days__lte=7, then=Value(5.0)),
                        When(course_age_days__lte=30, then=Value(2.0)),
                        default=Value(0.0)
                    )
                ) / (F('course_age_days') / 30.0 + 1.0),  # Age decay factor
                output_field=FloatField()
            )
        ).filter(
            trending_score__gt=0
        ).order_by('-trending_score')[:limit]
        
        return list(courses)
    
    def get_recommended_courses(self, limit=8) -> List[Course]:
        """
        Hybrid recommendation system combining multiple approaches
        """
        if not self.user:
            return self._get_popular_courses(limit)
        
        # Get user's enrolled courses
        user_courses = set(
            Enrollment.objects.filter(user=self.user)
            .values_list('course_id', flat=True)
        )
        
        if not user_courses:
            return self._get_popular_courses(limit)
        
        # Combine different recommendation approaches
        collaborative_recs = self._collaborative_filtering(user_courses)
        content_recs = self._content_based_filtering(user_courses)
        
        # Hybrid scoring
        course_scores = defaultdict(float)
        
        # Weight collaborative filtering recommendations
        for course_id, score in collaborative_recs.items():
            course_scores[course_id] += score * 0.6
        
        # Weight content-based recommendations
        for course_id, score in content_recs.items():
            course_scores[course_id] += score * 0.4
        
        # Exclude already enrolled courses
        for enrolled_course_id in user_courses:
            course_scores.pop(enrolled_course_id, None)
        
        # Sort by score and get top recommendations
        sorted_recommendations = sorted(
            course_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        if not sorted_recommendations:
            return self._get_popular_courses(limit)
        
        # Fetch Course objects
        course_ids = [course_id for course_id, _ in sorted_recommendations]
        courses = Course.objects.filter(id__in=course_ids)
        
        # Maintain order
        course_dict = {course.id: course for course in courses}
        return [course_dict[course_id] for course_id in course_ids if course_id in course_dict]
    
    def _collaborative_filtering(self, user_courses: set) -> Dict[int, float]:
        """
        Find users with similar course preferences and recommend their courses
        """
        # Find users who have enrolled in similar courses
        similar_users = User.objects.annotate(
            common_courses=Count(
                'enrollments',
                filter=Q(enrollments__course_id__in=user_courses)
            ),
            total_courses=Count('enrollments')
        ).filter(
            common_courses__gt=0,
            total_courses__gt=0
        ).exclude(id=self.user.id)
        
        course_scores = defaultdict(float)
        
        for similar_user in similar_users:
            # Calculate similarity score
            similarity = similar_user.common_courses / max(
                similar_user.total_courses, len(user_courses)
            )
            
            # Get courses this similar user has enrolled in
            similar_user_courses = Enrollment.objects.filter(
                user=similar_user
            ).exclude(
                course_id__in=user_courses
            ).values_list('course_id', flat=True)
            
            # Add weighted scores
            for course_id in similar_user_courses:
                course_scores[course_id] += similarity
        
        return course_scores
    
    def _content_based_filtering(self, user_courses: set) -> Dict[int, float]:
        """
        Recommend courses based on content similarity to user's enrolled courses
        """
        # Get user's enrolled course details
        enrolled_courses = Course.objects.filter(id__in=user_courses)
        
        # Extract user preferences
        user_creators = set(
            enrolled_courses.values_list('creator_id', flat=True)
        )
        user_price_ranges = self._get_price_preferences(enrolled_courses)
        
        course_scores = defaultdict(float)
        
        # Find courses by same creators
        creator_courses = Course.objects.filter(
            creator_id__in=user_creators
        ).exclude(id__in=user_courses)
        
        for course in creator_courses:
            course_scores[course.id] += 0.8
        
        # Find courses in similar price ranges
        similar_price_courses = Course.objects.filter(
            price__in=user_price_ranges
        ).exclude(id__in=user_courses)
        
        for course in similar_price_courses:
            course_scores[course.id] += 0.3
        
        # Boost newer courses slightly
        week_ago = self.current_time - timedelta(days=7)
        new_courses = Course.objects.filter(
            created_at__gte=week_ago
        ).exclude(id__in=user_courses)
        
        for course in new_courses:
            course_scores[course.id] += 0.2
        
        return course_scores
    
    def _get_price_preferences(self, courses) -> List[float]:
        """
        Determine user's price preferences based on enrolled courses
        """
        prices = [course.price for course in courses]
        if not prices:
            return [0.0]
        
        # Categorize prices
        price_ranges = []
        for price in prices:
            if price == 0:
                price_ranges.append(0.0)
            elif price <= 50:
                price_ranges.extend([0.0, 25.0, 50.0])
            elif price <= 100:
                price_ranges.extend([25.0, 50.0, 75.0, 100.0])
            else:
                price_ranges.extend([50.0, 100.0, 200.0])
        
        return list(set(price_ranges))
    
    def _get_popular_courses(self, limit: int) -> List[Course]:
        """
        Fallback: Get generally popular courses for new/anonymous users
        """
        return list(
            Course.objects.annotate(
                enrollment_count=Count('enrollments'),
                recent_enrollments=Count(
                    'enrollments',
                    filter=Q(
                        enrollments__enrolled_at__gte=
                        self.current_time - timedelta(days=30)
                    )
                ),
                popularity_score=F('enrollment_count') + F('recent_enrollments') * 2
            ).order_by('-popularity_score')[:limit]
        )
    
    def get_new_courses(self, limit=8) -> List[Course]:
        """
        Smart new courses with quality filtering
        """
        seven_days_ago = self.current_time - timedelta(days=7)
        
        new_courses = Course.objects.filter(
            created_at__gte=seven_days_ago
        ).annotate(
            # Quality indicators
            enrollment_count=Count('enrollments'),
            has_chapters=Count('chapter'),
            has_videos=Count('videometadata'),
            
            # Quality score
            quality_score=Case(
                When(
                    has_chapters__gt=0,
                    has_videos__gt=0,
                    then=F('enrollment_count') * 2 + F('has_chapters') + F('has_videos')
                ),
                default=F('enrollment_count'),
                output_field=FloatField()
            )
        ).order_by('-quality_score', '-created_at')[:limit]
        
        return list(new_courses)
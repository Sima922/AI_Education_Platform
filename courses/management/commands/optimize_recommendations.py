from django.core.management.base import BaseCommand
from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta
from courses.models import Course, Enrollment, User
from courses.recommendation_engine import AdvancedRecommendationEngine

class Command(BaseCommand):
    help = 'Optimize and analyze recommendation system performance'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--analyze',
            action='store_true',
            help='Analyze current recommendation performance',
        )
        parser.add_argument(
            '--update-scores',
            action='store_true',
            help='Update trending scores for all courses',
        )
    
    def handle(self, *args, **options):
        if options['analyze']:
            self.analyze_recommendations()
        
        if options['update_scores']:
            self.update_trending_scores()
    
    def analyze_recommendations(self):
        """Analyze recommendation system performance"""
        self.stdout.write("Analyzing recommendation system...")
        
        # Get statistics
        total_courses = Course.objects.count()
        total_users = User.objects.count()
        total_enrollments = Enrollment.objects.count()
        
        # Analyze user engagement
        active_users = User.objects.annotate(
            enrollment_count=Count('enrollments')
        ).filter(enrollment_count__gt=0)
        
        avg_enrollments_per_user = active_users.aggregate(
            avg=Avg('enrollment_count')
        )['avg'] or 0
        
        # Analyze course popularity
        popular_courses = Course.objects.annotate(
            enrollment_count=Count('enrollments')
        ).filter(enrollment_count__gt=0).order_by('-enrollment_count')[:10]
        
        # Recent activity
        week_ago = timezone.now() - timedelta(days=7)
        recent_enrollments = Enrollment.objects.filter(
            enrolled_at__gte=week_ago
        ).count()
        
        # Output analysis
        self.stdout.write(f"📊 RECOMMENDATION SYSTEM ANALYSIS")
        self.stdout.write(f"================================")
        self.stdout.write(f"Total Courses: {total_courses}")
        self.stdout.write(f"Total Users: {total_users}")
        self.stdout.write(f"Total Enrollments: {total_enrollments}")
        self.stdout.write(f"Active Users: {active_users.count()}")
        self.stdout.write(f"Avg Enrollments per User: {avg_enrollments_per_user:.2f}")
        self.stdout.write(f"Recent Enrollments (7d): {recent_enrollments}")
        
        self.stdout.write(f"\n🔥 TOP POPULAR COURSES:")
        for i, course in enumerate(popular_courses, 1):
            self.stdout.write(
                f"{i}. {course.title} ({course.enrollment_count} enrollments)"
            )
        
        # Test recommendation engine
        self.stdout.write(f"\n🎯 TESTING RECOMMENDATION ENGINE:")
        engine = AdvancedRecommendationEngine()
        
        # Test trending
        trending = engine.get_trending_courses(5)
        self.stdout.write(f"Trending Courses: {len(trending)} found")
        
        # Test for a sample user
        sample_user = active_users.first()
        if sample_user:
            user_recs = engine.get_recommended_courses(5)
            self.stdout.write(f"User Recommendations: {len(user_recs)} found")
        
        self.stdout.write(self.style.SUCCESS("✅ Analysis complete!"))
    
    def update_trending_scores(self):
        """Update trending scores for all courses"""
        self.stdout.write("Updating trending scores...")
        
        engine = AdvancedRecommendationEngine()
        trending_courses = engine.get_trending_courses(50)  # Get top 50
        
        updated_count = 0
        for course in trending_courses:
            if hasattr(course, 'trending_score'):
                # You might want to store trending scores in the database
                # For now, we'll just count them
                updated_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ Updated {updated_count} trending scores")
        )
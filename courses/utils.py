from .recommendation_engine import AdvancedRecommendationEngine

def get_smart_course_recommendations(user, limit=8):
    """
    Utility function to get smart course recommendations
    """
    engine = AdvancedRecommendationEngine(user)
    return engine.get_recommended_courses(limit)

def get_trending_courses(limit=8):
    """
    Utility function to get trending courses
    """
    engine = AdvancedRecommendationEngine()
    return engine.get_trending_courses(limit)

def get_quality_new_courses(limit=8):
    """
    Utility function to get quality new courses
    """
    engine = AdvancedRecommendationEngine()
    return engine.get_new_courses(limit)

def calculate_exam_score(answers):
    """Placeholder scoring function since AI is bypassed."""
    return 0  # Always return 0 or any default score

def generate_certificate_pdf(user, course):
    """Placeholder certificate generator."""
    return None


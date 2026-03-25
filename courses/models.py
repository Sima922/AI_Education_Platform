from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator
from django.conf import settings
import logging
import re
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


class User(AbstractUser):
    is_creator = models.BooleanField(default=False)
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_set',
        blank=True
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_set_permissions',
        blank=True
    )
    
    def get_social_account(self, provider='google'):
        """Safely get social account"""
        try:
            return self.socialaccount_set.get(provider=provider)
        except:
            return None
    
    def has_social_account(self, provider='google'):
        """Check if user has a social account"""
        return self.socialaccount_set.filter(provider=provider).exists()

class Course(models.Model):
    title = models.CharField(max_length=255)
    file_context = models.TextField(blank=True, null=True)
    keywords = models.JSONField(blank=True, null=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # Default is FREE
    thumbnail = models.ImageField(upload_to='thumbnails/', null=True, blank=True)
    creator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='courses'
    )
    created_at = models.DateTimeField(auto_now_add=True)

def __str__(self):
        return self.title    

class Topic(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='topics')
    title = models.CharField(max_length=255)
    description = models.TextField()
    files = models.ManyToManyField('File', related_name='associated_topics', blank=True)
    links = models.TextField(null=True, blank=True)

def __str__(self):
    return f"{self.title} - {self.course.title}"

class Chapter(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    content = models.TextField(null=True, blank=True)
    introduction = models.TextField(null=True, blank=True)
    learning_objectives = models.JSONField(null=True, blank=True)
    main_content = models.JSONField(null=True, blank=True)
    practical_examples = models.JSONField(null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    quiz = models.JSONField(null=True, blank=True)  # Structure: {"questions": [{"id": 1, "question": "...", "options": [...], "correct_answer": "...", "user_correct_answer": "...", "explanation": "..."}]}
    order = models.PositiveIntegerField()
    subtopics = models.JSONField(null=True, blank=True)
    files = models.ManyToManyField('File', related_name='associated_chapters', blank=True)
    links = models.TextField(null=True, blank=True)

class Meta:
    ordering = ['order']    

def __str__(self):
    return f"{self.order}. {self.title}"

class File(models.Model):
    file = models.FileField(upload_to='uploads/')
    file_type = models.CharField(
        max_length=50,
        choices=[
            ('image', 'Image'),
            ('link', 'Link'),
            ('document', 'Document'),
            ('resource', 'Resource')
        ],
        default='document'
    )

def __str__(self):
    return f"{self.file_type} - {self.file.name}"    

class Enrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    progress_data = models.JSONField(null=True, blank=True)  # Added field for tracking progress
    exam_eligible = models.BooleanField(default=False)
    exam_attempts_count = models.PositiveIntegerField(default=0)
    last_exam_attempt = models.DateTimeField(null=True, blank=True)
    certificate_earned = models.BooleanField(default=False)
    certificate_url = models.CharField(max_length=255, null=True, blank=True)

class Meta:
    unique_together = ('user', 'course')

def __str__(self):
    return f"{self.user.username} in {self.course.title}"



class VideoMetadata(models.Model):
    VIDEO_TYPES = (
        ('youtube', 'YouTube Video'),
        ('upload', 'Uploaded Video'),
    )

    chapter = models.ForeignKey('Chapter', on_delete=models.CASCADE, null=True)
    course = models.ForeignKey('Course', on_delete=models.CASCADE)
    video_type = models.CharField(max_length=10, choices=(('youtube','YouTube'),('upload','Upload')), default='youtube')
    
    title = models.CharField(max_length=255)
    description = models.TextField()
    youtube_url = models.URLField(blank=True, null=True)
    video_file = models.FileField(
        upload_to='course_videos/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'mov', 'avi'])]
    )
    relevance_point = models.CharField(max_length=255, default="General")

    def __str__(self):
        return f"Video: {self.title}"

    @property
    def youtube_id(self):
        """
        Extract ID from any standard YouTube URL (youtu.be/ID or youtube.com/watch?v=ID or /embed/ID).
        Returns empty string if no valid ID found.
        """
        url = (self.youtube_url or "").strip()
        if not url:
            return ""
        
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()

            # youtu.be/<id>
            if "youtu.be" in host:
                video_id = parsed.path.lstrip("/")
                # Remove any query parameters from the ID
                return video_id.split('?')[0] if video_id else ""

            # youtube.com/...v=ID or /embed/ID
            if "youtube.com" in host:
                # Check for v= parameter
                qs = parse_qs(parsed.query)
                if "v" in qs and qs["v"][0]:
                    return qs["v"][0]
                
                # Check for embed URL
                m = re.match(r"/embed/([^/?]+)", parsed.path)
                if m:
                    return m.group(1)
        except Exception:
            pass
        
        return ""

    @property
    def embed_url(self):
        """
        Only return a usable iframe URL if this is a YouTube video *and* we
        successfully extracted an ID.
        """
        if self.video_type == "youtube":
            vid = self.youtube_id
            if vid:
                return f"https://www.youtube.com/embed/{vid}"
        return ""

    @property
    def upload_url(self):
        """
        Return a direct URL to the stored file, or empty if none.
        """
        if self.video_type == "upload" and self.video_file:
            try:
                # Check if file exists
                if hasattr(self.video_file, 'url') and self.video_file.name:
                    return self.video_file.url
            except (ValueError, AttributeError):
                pass
        return ""

    def get_video_url(self):
        """
        Get the appropriate video URL based on video type
        """
        if self.video_type == "youtube":
            return self.embed_url
        elif self.video_type == "upload":
            return self.upload_url
        return ""

    def get_embed_url(self):
        """
        Get embeddable URL for any video type
        """
        return self.get_video_url()

    def get_youtube_id(self):
        """
        Public method to get YouTube ID
        """
        return self.youtube_id

    def is_video_available(self):
        """
        Check if the video is actually available
        """
        if self.video_type == "youtube":
            return bool(self.youtube_id)
        elif self.video_type == "upload":
            return bool(self.video_file and self.video_file.name)
        return False
             
 
class CourseDraft(models.Model):
    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    content = models.JSONField()
    thumbnail = models.ImageField(upload_to='draft_thumbnails/', null=True, blank=True)  # ADD THIS LINE
    form_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    exam_config = models.JSONField(null=True, blank=True)
    
    

def __str__(self):
    return f"Draft by {self.creator.username if self.creator else 'Anonymous'} - {self.created_at}"

class CourseVersion(models.Model):
    VERSION_TYPES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('auto-save', 'Auto Save'),
    )
    
    draft = models.ForeignKey(CourseDraft, on_delete=models.CASCADE, related_name='versions')
    content = models.JSONField()
    version_type = models.CharField(max_length=20, choices=VERSION_TYPES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

def __str__(self):
    return f"{self.version_type} version of {self.draft} at {self.created_at}"

class Meta:
    ordering = ['-created_at']
        
class ChatbotConversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
class ChatMessage(models.Model):
    conversation = models.ForeignKey(ChatbotConversation, related_name='messages', on_delete=models.CASCADE)
    message = models.TextField()
    is_user = models.BooleanField(default=False)  # True for user, False for bot
    timestamp = models.DateTimeField(auto_now_add=True)
    

class UserProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE)
    
    # Track different types of progress
    intro_read = models.BooleanField(default=False)
    objectives_read = models.BooleanField(default=False)
    content_read = models.BooleanField(default=False)
    videos_watched = models.JSONField(default=list)  # List of video IDs watched
    quiz_completed = models.BooleanField(default=False)
    quiz_score = models.FloatField(null=True, blank=True)
    
    # Overall chapter completion
    chapter_completed = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'course', 'chapter']
    
    def calculate_completion_percentage(self):
        """Calculate completion percentage for this chapter"""
        total_items = 5  # intro, objectives, content, videos, quiz
        completed_items = 0
        
        if self.intro_read:
            completed_items += 1
        if self.objectives_read:
            completed_items += 1
        if self.content_read:
            completed_items += 1
        if self.videos_watched:
            completed_items += 1
        if self.quiz_completed:
            completed_items += 1
            
        return (completed_items / total_items) * 100
    
    def mark_section_read(self, section_type):
        """Mark a section as read"""
        if section_type == 'intro':
            self.intro_read = True
        elif section_type == 'objectives':
            self.objectives_read = True
        elif section_type == 'content':
            self.content_read = True
        
        self.update_chapter_completion()
        self.save()
    
    def mark_video_watched(self, video_id):
        """Mark a video as watched"""
        if video_id not in self.videos_watched:
            self.videos_watched.append(video_id)
        self.update_chapter_completion()
        self.save()
    
    def mark_quiz_completed(self, score):
        """Mark quiz as completed with score"""
        self.quiz_completed = True
        self.quiz_score = score
        self.update_chapter_completion()
        self.save()
    
    def update_chapter_completion(self):
        """Update overall chapter completion status"""
        completion_percentage = self.calculate_completion_percentage()
        self.chapter_completed = completion_percentage >= 80  # 80% threshold for completion
        
class CourseExam(models.Model):
    """Main exam configuration for a course"""
    EXAM_TYPES = (
        ('default', 'Default Exam Style'),
        ('custom', 'Custom Prompt'),
        ('template', 'Uploaded Template'),
    )
    
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name='exam')
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPES, default='default')
    prompt = models.TextField(blank=True, null=True, help_text="Instructions for AI to generate exam")
    template_file = models.FileField(upload_to='exam_templates/', null=True, blank=True)
    is_enabled = models.BooleanField(default=False)
    time_limit_minutes = models.PositiveIntegerField(default=120)
    passing_score = models.FloatField(default=70.0)
    max_attempts = models.PositiveIntegerField(default=1)
    structure = models.JSONField(null=True, blank=True)  # AI-generated exam structure
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Exam for {self.course.title}"

class ExamQuestion(models.Model):
    """Individual questions in an exam"""
    QUESTION_TYPES = (
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
        ('essay', 'Essay'),
        ('practical', 'Practical'),
    )
    
    exam = models.ForeignKey(CourseExam, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    question_text = models.TextField()
    options = models.JSONField(null=True, blank=True)  # For multiple choice
    correct_answer = models.TextField(null=True, blank=True)
    points = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.question_type} question: {self.question_text[:50]}..."

class ExamSession(models.Model):
    """Individual exam attempt by a user"""
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('grading', 'Grading'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('flagged', 'Flagged for Review'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_sessions')
    exam = models.ForeignKey(CourseExam, on_delete=models.CASCADE, related_name='sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    score = models.FloatField(null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    tab_switch_count = models.PositiveIntegerField(default=0)
    fullscreen_exit_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ('user', 'exam')
    
    def __str__(self):
        return f"{self.user.username} - {self.exam.course.title} - {self.status}"

class ExamAnswer(models.Model):
    """Student's answers to exam questions"""
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE)
    answer_text = models.TextField(null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    points_earned = models.FloatField(default=0)
    graded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('session', 'question')
    
    def __str__(self):
        return f"Answer for question {self.question.id} in session {self.session.id}"

class ProctorLog(models.Model):
    """Log of proctoring events during an exam"""
    EVENT_TYPES = (
        ('tab_switch', 'Tab Switch'),
        ('fullscreen_exit', 'Fullscreen Exit'),
        ('face_not_visible', 'Face Not Visible'),
        ('multiple_faces', 'Multiple Faces Detected'),
        ('audio_detected', 'Audio Detected'),
        ('no_webcam', 'Webcam Disconnected'),
        ('system_check', 'System Check'),
    )
    
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='proctor_logs')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.event_type} at {self.timestamp} for session {self.session.id}"

class ExamResult(models.Model):
    """Final exam results and certificates"""
    session = models.OneToOneField(ExamSession, on_delete=models.CASCADE, related_name='result')
    score = models.FloatField()
    max_score = models.FloatField()
    percentage = models.FloatField()
    passed = models.BooleanField()
    graded_by_ai = models.BooleanField(default=True)
    reviewed_by_instructor = models.BooleanField(default=False)
    instructor_feedback = models.TextField(null=True, blank=True)
    certificate_generated = models.BooleanField(default=False)
    certificate_url = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Result for {self.session.user.username}: {self.percentage}%"                        
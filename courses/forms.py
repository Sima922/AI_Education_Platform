from django import forms
from django.core.validators import FileExtensionValidator
from .models import Course, Topic, Chapter, VideoMetadata, CourseExam, ExamResult


class CourseForm(forms.ModelForm):
    """
    Enhanced form for creating and updating courses with file support.
    """
    thumbnail = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/jpg'
            }
        ),
        help_text="Upload a thumbnail image for your course (required for display)"
    )
    
    course_files = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'form-control',
                'allow_multiple_selected': True,  # Fixed: use 'allow_multiple_selected' instead of 'multiple'
                'accept': '.pdf,.doc,.docx,.txt,.png,.jpg,.jpeg'
            }
        ),
        help_text="Upload supporting files (PDFs, documents, images)"
    )
    
    class Meta:
        model = Course
        fields = ['title', 'description', 'thumbnail']
        enable_exam = forms.BooleanField(
            required=False,
            widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            label="Include AI-Generated Exam",
            help_text="Check this box to include an AI-generated exam for this course"
            )
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter course title',
                'autocomplete': 'off'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter course description',
                'rows': 3
            }),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].widget.attrs.update({'autofocus': 'autofocus'})

class TopicForm(forms.ModelForm):
    """
    Enhanced form for topics with file support.
    """
    topic_files = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'form-control',
                'allow_multiple_selected': True,  # Fixed: use 'allow_multiple_selected' instead of 'multiple'
                'accept': '.pdf,.doc,.docx,.txt,.png,.jpg,.jpeg'
            }
        ),
        help_text="Upload supporting files for this topic"
    )
    
    class Meta:
        model = Topic
        fields = ['title', 'description', 'links']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter topic title',
                'autocomplete': 'off'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter topic description',
                'rows': 2
            }),
            'links': forms.URLInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter link to resource'
            }),
        }

class ChapterForm(forms.ModelForm):
    """
    Enhanced form for chapters with file support.
    """
    chapter_files = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'form-control',
                'allow_multiple_selected': True,  # Fixed: use 'allow_multiple_selected' instead of 'multiple'
                'accept': '.pdf,.doc,.docx,.txt,.png,.jpg,.jpeg'
            }
        ),
        help_text="Upload supporting files for this chapter"
    )
    
    class Meta:
        model = Chapter
        fields = ['title', 'content', 'links', 'order']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter chapter title',
                'autocomplete': 'off'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter chapter content',
                'rows': 2
            }),
            'links': forms.URLInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter link to resource'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter chapter order'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make fields optional for the formset
        self.fields['title'].required = False
        self.fields['content'].required = False
        self.fields['links'].required = False
        self.fields['order'].required = False
        self.fields['chapter_files'].required = False

class VideoForm(forms.Form):
    """
    Enhanced form for handling video uploads or YouTube links.
    """
    VIDEO_CHOICES = [
        ('youtube', 'YouTube Link'),
        ('upload', 'Video Upload'),
    ]

    video_type = forms.ChoiceField(
        choices=VIDEO_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'video-type-selector'}),
        initial='youtube',
        help_text="Select video source type"
    )
    youtube_url = forms.URLField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'https://www.youtube.com/watch?v=...',
            'class': 'form-control',
            'autocomplete': 'off'
        }),
        help_text="Paste a YouTube URL"
    )
    video_file = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(
            allowed_extensions=['mp4', 'mov', 'avi', 'mkv', 'webm']
        )],
        widget=forms.ClearableFileInput(attrs={
            'accept': 'video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm',
            'class': 'form-control'
        }),
        help_text="Upload a video file (max 2GB)"
    )
    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter video title',
            'class': 'form-control',
            'autocomplete': 'off'
        }),
        help_text="Title for your video"
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter video description (optional)',
            'class': 'form-control',
            'rows': 2
        }),
        required=False,
        help_text="Brief description of the video content"
    )

    def clean(self):
        cleaned_data = super().clean()
        video_type = cleaned_data.get('video_type')
        youtube_url = cleaned_data.get('youtube_url')
        video_file = cleaned_data.get('video_file')

        if video_type == 'youtube' and not youtube_url:
            raise forms.ValidationError("YouTube URL is required when video type is YouTube.")
        
        if video_type == 'upload' and not video_file:
            raise forms.ValidationError("Video file is required when video type is Upload.")
        
        # Validate YouTube URL format
        if video_type == 'youtube' and youtube_url:
            import re
            youtube_regex = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
            if not re.search(youtube_regex, youtube_url):
                raise forms.ValidationError("Please enter a valid YouTube URL.")
        
        # Validate file size for uploads (limit to 2GB)
        if video_type == 'upload' and video_file:
            if video_file.size > 2 * 1024 * 1024 * 1024:  # 2GB
                raise forms.ValidationError("Video file size must be less than 2GB.")

        return cleaned_data

class QuickVideoUploadForm(forms.Form):
    """
    Quick form for video uploads in preview mode
    """
    video_file = forms.FileField(
        validators=[FileExtensionValidator(
            allowed_extensions=['mp4', 'mov', 'avi', 'mkv', 'webm']
        )],
        widget=forms.ClearableFileInput(attrs={
            'accept': 'video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm',
            'class': 'form-control'
        }),
        help_text="Upload a video file (max 2GB)"
    )
    title = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter video title (optional)',
            'class': 'form-control',
            'autocomplete': 'off'
        })
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter video description (optional)',
            'class': 'form-control',
            'rows': 2
        }),
        required=False
    )

    def clean_video_file(self):
        video_file = self.cleaned_data.get('video_file')
        if video_file:
            # Check file size (2GB limit)
            if video_file.size > 2 * 1024 * 1024 * 1024:
                raise forms.ValidationError("Video file size must be less than 2GB.")
        return video_file

# Additional form from the first file that wasn't in the second
class FileForm(forms.Form):
    """
    Form for handling multiple file uploads.
    """
    files = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'form-control',
                'allow_multiple_selected': True,
                'placeholder': 'Select files to upload'
            }
        ),
        required=False
    )

class ExamConfigurationForm(forms.ModelForm):
    """
    Form for configuring exam settings during course creation
    """
    ENABLE_EXAM_CHOICES = [
        (False, 'No Exam'),
        (True, 'Generate AI Exam'),
    ]
    
    EXAM_TYPE_CHOICES = [
        ('default', 'Default Exam Style'),
        ('custom', 'Custom Prompt'),
        ('template', 'Upload Template'),
    ]
    
    enable_exam = forms.ChoiceField(
        choices=ENABLE_EXAM_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'exam-toggle'}),
        initial=False,
        label="Include Exam in Course"
    )
    
    exam_type = forms.ChoiceField(
        choices=EXAM_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        initial='default',
        required=False,
        label="Exam Generation Method"
    )
    
    exam_prompt = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Describe how you want the exam to be structured...'
        }),
        required=False,
        label="Exam Instructions"
    )
    
    template_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.doc,.docx,.txt'
        }),
        required=False,
        label="Upload Exam Template"
    )
    
    time_limit_minutes = forms.IntegerField(
        min_value=30,
        max_value=240,
        initial=120,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '120'
        }),
        required=False,
        label="Time Limit (minutes)"
    )
    
    passing_score = forms.FloatField(
        min_value=50,
        max_value=100,
        initial=70,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.1',
            'placeholder': '70.0'
        }),
        required=False,
        label="Passing Score (%)"
    )
    
    max_attempts = forms.IntegerField(
        min_value=1,
        max_value=5,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '1'
        }),
        required=False,
        label="Maximum Attempts"
    )
    
    class Meta:
        model = CourseExam
        fields = ['exam_type', 'prompt', 'time_limit_minutes', 'passing_score', 'max_attempts']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial values based on instance if editing
        if self.instance and self.instance.pk:
            self.fields['enable_exam'].initial = True
    
    def clean(self):
        cleaned_data = super().clean()
        enable_exam = cleaned_data.get('enable_exam')
        
        if enable_exam == 'True':
            # Validate exam configuration if enabled
            exam_type = cleaned_data.get('exam_type')
            exam_prompt = cleaned_data.get('exam_prompt')
            template_file = cleaned_data.get('template_file')
            
            if exam_type == 'custom' and not exam_prompt:
                raise forms.ValidationError("Please provide exam instructions for custom exam generation.")
            
            if exam_type == 'template' and not template_file:
                raise forms.ValidationError("Please upload an exam template file.")
        
        return cleaned_data

class ExamPreflightForm(forms.Form):
    """
    Form for pre-exam verification and agreement
    """
    full_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your full name as it should appear on the certificate'
        }),
        label="Full Name"
    )
    
    agree_terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I agree to the exam terms and conditions"
    )
    
    agree_proctoring = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I agree to enable webcam and microphone for proctoring"
    )
    
    confirm_ready = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I confirm I'm ready to start the exam and won't leave the page"
    )
    
    def clean_full_name(self):
        full_name = self.cleaned_data.get('full_name')
        if len(full_name.strip().split()) < 2:
            raise forms.ValidationError("Please enter your full first and last name.")
        return full_name

class ExamReviewForm(forms.ModelForm):
    """
    Form for instructors to review and adjust exam results
    """
    adjustment_reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Explain why you are adjusting the score...'
        }),
        required=False,
        label="Adjustment Reason"
    )
    
    class Meta:
        model = ExamResult
        fields = ['score', 'instructor_feedback', 'reviewed_by_instructor']
        widgets = {
            'score': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1',
                'min': '0',
                'max': '100'
            }),
            'instructor_feedback': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Provide feedback to the student...'
            }),
            'reviewed_by_instructor': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def clean_score(self):
        score = self.cleaned_data.get('score')
        if score is not None and (score < 0 or score > 100):
            raise forms.ValidationError("Score must be between 0 and 100.")
        return score

# Add this form for students to provide feedback on exams
class ExamFeedbackForm(forms.Form):
    """
    Form for students to provide feedback on the exam experience
    """
    RATING_CHOICES = [
        (1, 'Very Difficult'),
        (2, 'Difficult'),
        (3, 'Moderate'),
        (4, 'Easy'),
        (5, 'Very Easy'),
    ]
    
    difficulty_rating = forms.ChoiceField(
        choices=RATING_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="How would you rate the difficulty of this exam?"
    )
    
    relevance_rating = forms.ChoiceField(
        choices=RATING_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="How relevant was the exam to the course content?"
    )
    
    feedback = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Share any additional feedback about the exam...'
        }),
        required=False,
        label="Additional Feedback"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        # Additional validation if needed
        return cleaned_data        
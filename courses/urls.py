from django.urls import path
from django.conf import settings
from allauth.account.views import LoginView, SignupView
from .auth_views import SignUpView, custom_logout_view, profile_view, auth_status
from django.conf.urls.static import static
from .course_management import (
    homepage, preview_course, create_course, view_course, 
    create_course_with_prompt, save_draft_version, restore_version, update_course_content, reorder_chapters, delete_chapter, debug_course_videos, debug_video_paths, get_course_recommendations, track_progress, edit_course, delete_course,
)
from .video_management import add_video, upload_video, add_youtube_video, debug_video_status
from .quiz_management import submit_quiz, reset_quiz
from .chatbot_views import start_chatbot_session, chatbot_interact, get_course_info
from .views import (
    CourseListCreateView,
    CourseDetailView,
    EnrollInCourseView,
    UserProfileView,
    enroll_in_course,
    smart_search,
    track_section_progress,
    track_video_progress,
    get_user_progress,
)
from .exam_views import (
    configure_exam_settings,
    exam_eligibility_check,
    exam_preflight_check,
    start_exam_session,
    exam_interface,
    submit_exam,
    exam_results,
    certificate_view,
)

app_name = 'courses'

urlpatterns = [
    # Home and basic pages
    path("", homepage, name="homepage"),
    path("profile/", UserProfileView.as_view(), name="user_profile"),

    # Course listing and creation
    path("courses/", CourseListCreateView.as_view(), name="course_list"),
    path("courses/create/", create_course, name="create_course"),
    path('create-with-prompt/', create_course_with_prompt, name='create_with_prompt'),
    path('debug-videos/<int:course_id>/', debug_course_videos, name='debug_course_videos'),
    path('debug-videos/<int:course_id>/', debug_video_paths, name='debug_video_paths'),

    # Course preview and draft management
    path('preview/<int:draft_id>/', preview_course, name='preview_course'),

    path("courses/preview/<int:draft_id>/", preview_course, name="preview_draft"),
    path('courses/smart-search/', smart_search, name='smart_search'),
    path("courses/<int:course_id>/edit/", edit_course, name="edit_course"),
    path("courses/<int:course_id>/delete/", delete_course, name="delete_course"),
    
    # Draft versioning and management
    path("drafts/<int:draft_id>/save-version/", save_draft_version, name="save_draft_version"),
    path("versions/<int:version_id>/restore/", restore_version, name="restore_version"),
    path("chapters/<int:chapter_id>/track-progress/", track_progress, name="track_progress"),
    
    # Progress tracking URLs
    path('courses/track-section/', track_section_progress, name='track_section_progress'),
    path('courses/track-video/', track_video_progress, name='track_video_progress'),
    path('courses/progress/<int:course_id>/', get_user_progress, name='get_user_progress'),

    # Course content management
    path("drafts/<int:draft_id>/update-content/", update_course_content, name="update_course_content"),
    path("drafts/<int:draft_id>/reorder-chapters/", reorder_chapters, name="reorder_chapters"),
    path("drafts/<int:draft_id>/delete-chapter/", delete_chapter, name="delete_chapter"),
    
    # Authentication URLs
    path('login/', LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/login/', LoginView.as_view(template_name='registration/login.html'), name='account_login'),
    path('accounts/signup/', SignupView.as_view(template_name='registration/signup.html'), name='account_signup'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('custom-logout/', custom_logout_view, name='custom_logout'),
    path('profile/', profile_view, name='profile'),
    path('api/auth-status/', auth_status, name='auth_status'),
    
    # Video management
    path("drafts/<int:draft_id>/upload-video/", upload_video, name="upload_video"),
    path("add-youtube-video/", add_youtube_video, name="add_youtube_video"),
    path("chapters/<int:chapter_id>/add-video/", add_video, name="add_video"),
    path('debug-video-status/<int:course_id>/', debug_video_status, name='debug_video_status'),
    
    # Smart recommendation APIs
    path('api/recommendations/', get_course_recommendations, name='api_recommendations'),

    # Course viewing and interaction
    path("view_course/<int:pk>/", view_course, name="view_course"),
    path("courses/<int:pk>/api/", CourseDetailView.as_view(), name="course_detail_api"),
    path("courses/<int:course_id>/enroll/", EnrollInCourseView.as_view(), name="enroll_course"),
    path("courses/<int:course_id>/enroll-form/", enroll_in_course, name="enroll_course_form"),
    path('course/<int:course_id>/chat/start/', start_chatbot_session, name='start_chat_session'),
    path('chat/<int:conversation_id>/', chatbot_interact, name='chatbot_interact'),

    # Quiz submission
    path("chapters/<int:chapter_id>/submit-quiz/", submit_quiz, name="submit_quiz"),
    path('chapter/<int:chapter_id>/reset-quiz/', reset_quiz, name='reset_quiz'),
    
    # Exam management
    path("courses/<int:course_id>/configure-exam/", configure_exam_settings, name="configure_exam"),
    path("courses/<int:course_id>/exam-eligibility/", exam_eligibility_check, name="exam_eligibility"),
    path("courses/<int:course_id>/exam-preflight/", exam_preflight_check, name="exam_preflight"),
    path("courses/<int:course_id>/start-exam/", start_exam_session, name="start_exam"),
    path("exams/<int:session_id>/interface/", exam_interface, name="exam_interface"),
    path("exams/<int:session_id>/submit/", submit_exam, name="submit_exam"),
    path("exams/<int:session_id>/results/", exam_results, name="exam_results"),
    path("courses/<int:course_id>/certificate/", certificate_view, name="certificate"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
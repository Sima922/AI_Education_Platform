from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Course, Topic, Chapter, File, Enrollment, VideoMetadata

class CourseFilter(admin.SimpleListFilter):
    title = 'course'
    parameter_name = 'course'

    def lookups(self, request, model_admin):
        courses = Course.objects.all()
        return [(course.id, course.title) for course in courses]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(course_id=self.value())
        return queryset

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('is_creator',)}),
    )
    list_display = UserAdmin.list_display + ('is_creator',)
    list_filter = UserAdmin.list_filter + ('is_creator',)

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'creator', 'created_at')
    list_filter = ('creator', 'created_at')
    search_fields = ('title', 'description')
    ordering = ('-created_at',)

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'course')
    list_filter = ('course',)
    search_fields = ('title', 'description')
    filter_horizontal = ('files',)

@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('title', 'content')
    filter_horizontal = ('files',)
    ordering = ('order',)
    
    fields = (
        'course', 'title', 'content', 'order',
        'introduction', 'summary', 'subtopics',
        'learning_objectives', 'main_content', 'practical_examples',
        'quiz', 'files', 'links'
    )

@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ('file', 'file_type')
    list_filter = ('file_type',)
    search_fields = ('file',)

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'enrolled_at')
    list_filter = ('enrolled_at',)
    search_fields = ('user__username', 'course__title')
    ordering = ('-enrolled_at',)

@admin.register(VideoMetadata)
class VideoMetadataAdmin(admin.ModelAdmin):
    list_display = ('title', 'get_course', 'get_video_url')
    search_fields = ('title', 'course__title')
    fields = ('course', 'chapter', 'title', 'description', 'video_type', 'youtube_url', 'video_file', 'relevance_point')

    def get_course(self, obj):
        return obj.course.title
    get_course.short_description = 'Course'
    get_course.admin_order_field = 'course__title'

    def get_video_url(self, obj):
        return obj.get_video_url()
    get_video_url.short_description = "Video URL"

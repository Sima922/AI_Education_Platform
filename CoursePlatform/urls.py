from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("courses.urls")),  # Include courses app URLs
    path("api/auth/", include("rest_framework.urls")),  # DRF login/logout
    path("accounts/", include("allauth.urls")),  # Allauth Authentication
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("courses/", include("courses.urls")),
    path("courses/<int:course_id>/", include("materials.urls")),
    path("courses/<int:course_id>/assignments/", include("assignments.urls")),
    path("", include("assessments.urls")),
    path("healthz", core_views.healthz, name="healthz"),
    path("", core_views.home, name="home"),
]

from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.list_courses, name="list"),
    path("new/", views.create_course, name="create"),
    path("<int:course_id>/", views.detail, name="detail"),
    path("<int:course_id>/archive/", views.archive, name="archive"),
    path("<int:course_id>/trash/", views.trash, name="trash"),
    path("<int:course_id>/trash/<str:kind>/<int:item_id>/restore/", views.trash_restore, name="trash_restore"),
    path("<int:course_id>/trash/<str:kind>/<int:item_id>/delete/", views.trash_delete, name="trash_delete"),
    path("<int:course_id>/roster/upload/", views.roster_upload, name="roster_upload"),
    path("<int:course_id>/students/<int:user_id>/<str:action>/",
         views.enrollment_toggle, name="enrollment_toggle"),
]

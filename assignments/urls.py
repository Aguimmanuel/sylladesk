from django.urls import path

from . import views

app_name = "assignments"

urlpatterns = [
    path("new/", views.create, name="create"),
    path("<int:assignment_id>/", views.detail, name="detail"),
    path("<int:assignment_id>/edit/", views.edit, name="edit"),
    path("<int:assignment_id>/delete/", views.delete, name="delete"),
    path("<int:assignment_id>/submit/", views.submit, name="submit"),
    path("<int:assignment_id>/submissions/<int:submission_id>/download/",
         views.submission_download, name="submission_download"),
    path("<int:assignment_id>/submissions/<int:submission_id>/view/",
         views.submission_view, name="submission_view"),
    path("<int:assignment_id>/submissions/<int:submission_id>/grade/",
         views.grade, name="grade"),
]

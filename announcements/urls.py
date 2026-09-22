from django.urls import path

from . import views

app_name = "announcements"

urlpatterns = [
    path("", views.create, name="create"),
    path("<int:announcement_id>/edit/", views.edit, name="edit"),
    path("<int:announcement_id>/delete/", views.delete, name="delete"),
]

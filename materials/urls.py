from django.urls import path

from . import views

app_name = "materials"

urlpatterns = [
    path("materials/upload/", views.upload, name="upload"),
    path("materials/<int:material_id>/download/", views.download, name="download"),
    path("materials/<int:material_id>/delete/", views.delete, name="delete"),
]

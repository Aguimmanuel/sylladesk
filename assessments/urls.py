from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("courses/<int:course_id>/tests/new/", views.create, name="create"),
    path("courses/<int:course_id>/tests/<int:test_id>/", views.detail, name="detail"),
    path("courses/<int:course_id>/tests/<int:test_id>/questions/add/", views.add_question, name="add_question"),
    path("courses/<int:course_id>/tests/<int:test_id>/questions/<int:question_id>/delete/",
         views.delete_question, name="delete_question"),
    path("courses/<int:course_id>/tests/<int:test_id>/code/", views.regenerate, name="regenerate"),
    path("courses/<int:course_id>/tests/<int:test_id>/release/", views.release, name="release"),
    path("tests/join/", views.join_box, name="join_box"),
    path("tests/join/<str:code>/", views.join, name="join"),
    path("tests/join/<str:code>/take/", views.take, name="take"),
    path("tests/join/<str:code>/save/", views.save, name="save"),
    path("tests/join/<str:code>/submit/", views.submit_test, name="submit_test"),
]

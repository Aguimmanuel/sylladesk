from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("courses/<int:course_id>/tests/new/", views.create, name="create"),
    path("courses/<int:course_id>/tests/<int:test_id>/", views.detail, name="detail"),
    path("courses/<int:course_id>/tests/<int:test_id>/edit/", views.edit, name="edit"),
    path("courses/<int:course_id>/tests/<int:test_id>/start/", views.start, name="start"),
    path("courses/<int:course_id>/tests/<int:test_id>/close/", views.close, name="close"),
    path("courses/<int:course_id>/tests/<int:test_id>/reopen/", views.reopen, name="reopen"),
    path("courses/<int:course_id>/tests/<int:test_id>/archive/", views.archive, name="archive"),
    path("courses/<int:course_id>/tests/<int:test_id>/restore/", views.restore, name="restore"),
    path("courses/<int:course_id>/tests/<int:test_id>/questions/add/", views.add_question, name="add_question"),
    path("courses/<int:course_id>/tests/<int:test_id>/questions/<int:question_id>/delete/",
         views.delete_question, name="delete_question"),
    path("courses/<int:course_id>/tests/<int:test_id>/code/", views.regenerate, name="regenerate"),
    path("courses/<int:course_id>/tests/<int:test_id>/clone/", views.clone, name="clone"),
    path("courses/<int:course_id>/tests/<int:test_id>/attempts/", views.attempts_fragment, name="attempts_fragment"),
    path("courses/<int:course_id>/tests/<int:test_id>/attempts/<int:attempt_id>/",
         views.attempt_detail, name="attempt"),
    path("courses/<int:course_id>/tests/<int:test_id>/students/", views.set_students, name="set_students"),
    path("courses/<int:course_id>/tests/<int:test_id>/release/", views.release, name="release"),
    path("tests/join/", views.join_box, name="join_box"),
    path("tests/join/<str:code>/status/", views.status, name="status"),
    path("tests/join/<str:code>/", views.join, name="join"),
    path("tests/join/<str:code>/take/", views.take, name="take"),
    path("tests/join/<str:code>/save/", views.save, name="save"),
    path("tests/join/<str:code>/advance/", views.advance, name="advance"),
    path("tests/join/<str:code>/submit/", views.submit_test, name="submit_test"),
]

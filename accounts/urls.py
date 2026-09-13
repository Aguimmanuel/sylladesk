from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("password/set/", views.PasswordSetView.as_view(), name="password_set"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password_change"),
    path("signup/", views.StudentSignupView.as_view(), name="signup"),
]

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("signup/", views.StudentSignupView.as_view(), name="signup"),
    path("password/set/", views.PasswordSetView.as_view(), name="password_set"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password_change"),
    path("password/reset/", views.ThrottledPasswordResetView.as_view(), name="password_reset"),
    path("password/reset/done/", views.PasswordResetDone.as_view(), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", views.ResetConfirm.as_view(), name="password_reset_confirm"),
    path("password/reset/complete/", views.PasswordResetComplete.as_view(), name="password_reset_complete"),
]

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.urls import path
from django.shortcuts import redirect, render
from django.contrib import messages

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "full_name", "email", "global_role", "is_active",
                    "must_reset_password", "last_login")
    list_filter = ("global_role", "is_active", "must_reset_password")
    search_fields = ("username", "full_name", "email", "reg_no")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Identity", {"fields": ("full_name", "email", "reg_no", "global_role")}),
        ("Access", {"fields": ("is_active", "is_staff", "must_reset_password")}),
        ("Dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "full_name", "email", "global_role", "password1", "password2"),
        }),
    )
    ordering = ("username",)


@admin.action(description="Force password reset at next login")
def force_password_reset(modeladmin, request, queryset):
    from core.auditing import audit
    count = 0
    for user in queryset:
        user.must_reset_password = True
        user.set_unusable_password()
        user.save(update_fields=["password", "must_reset_password"])
        audit(actor=request.user, action="auth.force_reset", obj=user)
        count += 1
    modeladmin.message_user(request, f"{count} account(s) will set a new password at next login.")


UserAdmin.actions = [force_password_reset]

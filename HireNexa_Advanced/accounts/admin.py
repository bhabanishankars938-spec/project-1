from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, OTPChallenge, OTPAttempt, VerificationEvent, AuditLog, PlatformSetting,
    UserSettings, NotificationPreference, LoginHistory
)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("HireNexa Profile & Role", {"fields": ("role", "phone_number", "is_email_verified", "is_phone_verified", "email_verified_at", "phone_verified_at")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("HireNexa Profile & Role", {"fields": ("role", "phone_number")}),
    )
    list_display = ("username", "email", "phone_number", "role", "is_email_verified", "is_phone_verified", "is_active", "is_staff")
    list_filter = ("role", "is_email_verified", "is_phone_verified", "is_active", "is_staff")
    search_fields = ("username", "email", "phone_number", "first_name", "last_name")


@admin.register(OTPChallenge)
class OTPChallengeAdmin(admin.ModelAdmin):
    list_display = ("recipient", "channel", "purpose", "delivery_status", "provider_name", "attempts_left", "is_used", "created_at", "expires_at")
    list_filter = ("channel", "purpose", "delivery_status", "is_used")
    search_fields = ("recipient", "provider_reference_id")
    readonly_fields = ("otp_hash", "created_at", "verified_at")


@admin.register(OTPAttempt)
class OTPAttemptAdmin(admin.ModelAdmin):
    list_display = ("challenge", "ip_address", "is_successful", "error_reason", "timestamp")
    list_filter = ("is_successful",)
    search_fields = ("challenge__recipient", "ip_address")


@admin.register(VerificationEvent)
class VerificationEventAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "channel", "recipient", "ip_address", "timestamp")
    list_filter = ("event_type", "channel")
    search_fields = ("recipient", "user__username")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "resource_type", "resource_id", "ip_address", "timestamp")
    list_filter = ("action", "resource_type")
    search_fields = ("user__username", "action", "ip_address")


@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "updated_at")
    search_fields = ("key",)


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "theme", "timezone", "language", "two_factor_enabled", "profile_visibility", "updated_at")
    list_filter = ("theme", "two_factor_enabled", "profile_visibility")
    search_fields = ("user__username", "user__email", "headline", "location")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "digest_frequency", "email_job_alerts", "email_applications", "push_enabled", "updated_at")
    list_filter = ("digest_frequency", "push_enabled")
    search_fields = ("user__username", "user__email")


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "ip_address", "device_type", "is_active", "created_at")
    list_filter = ("is_active", "device_type")
    search_fields = ("user__username", "ip_address", "user_agent")


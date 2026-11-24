from django.urls import path
from accounts import views_settings as views

urlpatterns = [
    path("", views.settings_index_view, name="settings_index"),
    path("profile/", views.settings_profile_view, name="settings_profile"),
    path("account/", views.settings_account_view, name="settings_account"),
    path("security/", views.settings_security_view, name="settings_security"),
    path("notifications/", views.settings_notifications_view, name="settings_notifications"),
    path("privacy/", views.settings_privacy_view, name="settings_privacy"),
    path("appearance/", views.settings_appearance_view, name="settings_appearance"),
    path("connected-accounts/", views.settings_connected_accounts_view, name="settings_connected_accounts"),
    
    # Candidate & Freelancer specific
    path("preferences/", views.settings_preferences_view, name="settings_preferences"),
    path("payout/", views.settings_payout_view, name="settings_payout"),
    
    # HR & Recruiter specific
    path("company/", views.settings_company_view, name="settings_company"),
    path("team/", views.settings_team_view, name="settings_team"),
    
    # Platform Owner specific
    path("platform/", views.settings_platform_view, name="settings_platform"),
]

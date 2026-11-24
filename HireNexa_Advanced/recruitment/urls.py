from django.urls import path
from . import views, api_views, views_innovation

urlpatterns = [
    # Public & Dashboard Routing
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile_edit, name="profile_edit"),

    # India Location Autocomplete & Hierarchy APIs
    path("api/locations/autocomplete/", api_views.location_autocomplete_api, name="location_autocomplete_api"),
    path("api/locations/autocomplete/lookup/", api_views.location_autocomplete_api, name="location_autocomplete"),
    path("api/locations/hierarchy/", api_views.location_hierarchy_api, name="location_hierarchy_api"),
    path("api/locations/hierarchy/tree/", api_views.location_hierarchy_api, name="location_hierarchy"),

    # Platform Owner Master Control
    path("owner/", views.owner_dashboard, name="owner_dashboard"),
    path("owner/dashboard/", views.owner_dashboard, name="owner_dashboard_alias"),
    path("owner/orgs/<int:pk>/toggle/", views.owner_toggle_org, name="owner_toggle_org"),
    path("owner/orgs/<int:pk>/approve/", views.owner_approve_org, name="owner_approve_org"),
    path("owner/orgs/<int:pk>/reject/", views.owner_reject_org, name="owner_reject_org"),
    path("owner/orgs/<int:pk>/detail/", views.owner_company_detail, name="owner_company_detail"),
    path("owner/reports/<int:pk>/resolve/", views.owner_resolve_report, name="owner_resolve_report"),
    path("owner/docs/<int:pk>/review/", views.owner_review_doc, name="owner_review_doc"),
    path("owner/plans/", views.owner_plans_list, name="owner_plans_list"),
    path("owner/plans/create/", views.owner_create_plan, name="owner_create_plan"),
    path("owner/plans/<int:pk>/edit/", views.owner_edit_plan, name="owner_edit_plan"),
    path("owner/plans/<int:pk>/delete/", views.owner_delete_plan, name="owner_delete_plan"),
    path("owner/users/<int:pk>/toggle/", views.owner_toggle_user_status, name="owner_toggle_user_status"),
    path("owner/users/<int:pk>/role/", views.owner_change_user_role, name="owner_change_user_role"),
    path("owner/jobs/<int:pk>/toggle-featured/", views.owner_toggle_job_featured, name="owner_toggle_job_featured"),
    path("owner/settings/update/", views.owner_update_setting, name="owner_update_setting"),
    path("owner/export-report/", views.owner_export_report, name="owner_export_report"),

    # Company Admin Workspace
    path("company/", views.company_dashboard, name="company_dashboard"),
    path("company/dashboard/", views.company_dashboard, name="company_dashboard_alias"),
    path("company/add-hr/", views.company_add_hr, name="company_add_hr"),
    path("company/profile/edit/", views.company_profile_edit, name="company_profile_edit"),

    # HR Recruiter Workspace
    path("hr/", views.hr_dashboard, name="hr_dashboard"),
    path("hr/dashboard/", views.hr_dashboard, name="hr_dashboard_alias"),
    path("recruiter/dashboard/", views.hr_dashboard, name="recruiter_dashboard"),

    # Candidate Portal & Enrichment
    path("candidate/", views.candidate_dashboard, name="candidate_dashboard"),
    path("candidate/dashboard/", views.candidate_dashboard, name="candidate_dashboard_alias"),
    path("candidate/applications/", views.candidate_dashboard, name="candidate_applications"),
    path("candidate/saved-jobs/", views.candidate_saved_jobs, name="saved_jobs"),
    path("pricing/", views.pricing_view, name="pricing"),
    path("pricing/plans/", views.pricing_view, name="pricing_plans"),
    path("premium/", views.pricing_view, name="premium"),
    path("candidate/education/add/", views.candidate_education_add, name="candidate_education_add"),
    path("candidate/skill/add/", views.candidate_skill_add, name="candidate_skill_add"),
    path("candidate/project/add/", views.candidate_project_add, name="candidate_project_add"),
    path("candidate/consent/toggle/", views.candidate_consent_toggle, name="candidate_consent_toggle"),
    path("candidate/delete-account/", views.candidate_delete_account, name="candidate_delete_account"),

    # Candidate Project Portfolio (Supabase Storage Powered)
    path("candidate/portfolio/", views.candidate_portfolio_list, name="candidate_portfolio_list"),
    path("candidate/portfolio/create/", views.candidate_project_create, name="candidate_project_create"),
    path("candidate/portfolio/<int:pk>/edit/", views.candidate_project_edit, name="candidate_project_edit"),
    path("candidate/portfolio/<int:pk>/delete/", views.candidate_project_delete, name="candidate_project_delete"),
    path("candidate/portfolio/files/<int:pk>/delete/", views.candidate_project_file_delete, name="candidate_project_file_delete"),
    path("portfolio/files/<int:pk>/download/", views.candidate_project_file_download, name="candidate_project_file_download"),
    path("portfolio/files/<int:pk>/preview/", views.candidate_project_file_preview, name="candidate_project_file_preview"),
    path("hr/candidate/<int:candidate_id>/portfolio/", views.hr_candidate_portfolio_view, name="hr_candidate_portfolio_view"),

    # Freelancer Workspace & Projects
    path("freelancer/", views.freelancer_dashboard, name="freelancer_dashboard"),
    path("freelancer/dashboard/", views.freelancer_dashboard, name="freelancer_dashboard_alias"),
    path("freelancer/profile/", views.freelancer_profile_edit, name="freelancer_profile_edit"),
    path("projects/", views.project_list, name="project_list"),
    path("projects/create/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/apply/", views.project_apply, name="project_apply"),

    # Job Management (Multi-tenant)
    path("jobs/", views.job_list, name="job_list"),
    path("jobs/create/", views.job_create, name="job_create"),
    path("jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("jobs/<int:pk>/edit/", views.job_edit, name="job_edit"),
    path("jobs/<int:pk>/duplicate/", views.job_duplicate, name="job_duplicate"),
    path("jobs/<int:pk>/delete/", views.job_delete, name="job_delete"),
    path("jobs/<int:pk>/headcount/", views.job_headcount_adjust, name="job_headcount_adjust"),
    path("jobs/<int:pk>/toggle-status/", views.job_toggle_status, name="job_toggle_status"),
    path("jobs/<int:pk>/apply/", views.apply_job, name="apply_job"),
    path("jobs/<int:pk>/applicants/", views.applicants, name="applicants"),

    # News & Announcements Broadcast Engine
    path("news/", views.news_list, name="news_list"),
    path("news/create/", views.news_create, name="news_create"),
    path("news/<slug:slug>/", views.news_detail, name="news_detail"),
    path("news/<int:pk>/edit/", views.news_edit, name="news_edit"),
    path("news/<int:pk>/delete/", views.news_delete, name="news_delete"),

    # Application Evaluation & Interviews
    path("applications/<int:pk>/status/", views.update_application_status, name="update_application_status"),
    path("applications/<int:pk>/interview/", views.schedule_interview, name="schedule_interview"),
    path("interviews/<int:pk>/reschedule/", views.reschedule_interview, name="reschedule_interview"),
    path("interviews/<int:pk>/cancel/", views.cancel_interview, name="cancel_interview"),
    path("interviews/<int:pk>/lobby/", views.interview_lobby, name="interview_lobby"),
    path("interviews/<int:pk>/room/", views.interview_room, name="interview_room"),
    path("api/interviews/<int:pk>/signal/", api_views.interview_signal_api, name="interview_signal_api"),
    path("api/interviews/<int:pk>/feedback/", api_views.interview_feedback_api, name="interview_feedback_api"),

    # Resume Storage & Secure Download
    path("resumes/upload/", views.resume_upload, name="resume_upload"),
    path("resumes/<int:pk>/download/", views.download_resume, name="download_resume"),
    path("resumes/<int:pk>/preview/", views.preview_resume, name="preview_resume"),
    path("resumes/<int:pk>/delete/", views.delete_resume, name="delete_resume"),

    # Startup Platform Modules: Companies, AI Resume Analyzer, Resources, Legal
    path("companies/", views.companies_list, name="companies_list"),
    path("resume-analyzer/", views.resume_analyzer, name="resume_analyzer"),
    path("resources/", views.career_resources, name="career_resources"),
    path("terms/", views.terms_view, name="terms"),
    path("privacy/", views.privacy_view, name="privacy"),

    # Candidate Job Saving & Recommendations
    path("jobs/<int:pk>/save/", views.toggle_save_job, name="toggle_save_job"),
    path("jobs/saved/", views.candidate_saved_jobs, name="candidate_saved_jobs"),
    path("jobs/recommended/", views.candidate_recommended_jobs, name="candidate_recommended_jobs"),
    path("applications/<int:pk>/withdraw/", views.withdraw_application, name="withdraw_application"),
    path("report/", views.report_listing, name="report_listing"),

    # Company Verification & In-App Notifications
    path("company/verification-upload/", views.company_verification_upload, name="company_verification_upload"),
    path("notifications/", views.notifications_view, name="notifications_view"),
    path("notifications/mark-read/", views.mark_all_notifications_read, name="mark_all_notifications_read"),

    # Editorial, Support & Career More Hub
    path("about/", views.about_view, name="about"),
    path("contact/", views.contact_view, name="contact"),
    path("career-guidance/", views.career_guidance_view, name="career_guidance"),
    path("interview-prep/", views.interview_prep_view, name="interview_prep"),
    path("resume-builder/", views.resume_builder_view, name="resume_builder"),
    path("salary-insights/", views.salary_insights_view, name="salary_insights"),
    path("help/", views.help_center_view, name="help_center"),
    path("faq/", views.faq_view, name="faq"),

    # Advanced Innovation Systems & AI Career Optimization (ACO)
    path("candidate/career-assistant/", views_innovation.candidate_career_assistant_view, name="candidate_career_assistant"),
    path("career/aco/", views_innovation.candidate_career_assistant_view, name="career_aco"),
    path("career-assistant/", views_innovation.candidate_career_assistant_view, name="career_assistant_alias"),
    path("market-intelligence/", views_innovation.market_intelligence_view, name="market_intelligence"),
    path("api/v1/market-intelligence/", views_innovation.market_intelligence_api, name="api_market_intelligence"),
    path("jobs/discovery/", views_innovation.job_discovery_view, name="job_discovery"),
    path("jobs/nearby/", views_innovation.location_discovery_view, name="location_discovery"),
    path("jobs/<int:job_id>/report/", views_innovation.report_suspicious_job_view, name="report_suspicious_job"),
    path("companies/<int:pk>/trust/", views_innovation.company_trust_view, name="company_trust_profile"),
    path("learning-paths/", views_innovation.learning_paths_view, name="learning_paths"),
    path("learning-paths/<slug:slug>/", views_innovation.learning_path_detail_view, name="learning_path_detail"),
    path("candidate/passport/", views_innovation.candidate_passport_view, name="candidate_passport"),
    path("passport/<str:passport_id>/", views_innovation.public_passport_verify_view, name="public_passport_verify"),
    path("hr/intelligence/", views_innovation.recruiter_intelligence_view, name="recruiter_intelligence"),
    path("notifications/center/", views_innovation.notifications_center_view, name="notifications_center"),
    path("owner/intelligence/", views_innovation.data_intelligence_view, name="data_intelligence_center"),
]

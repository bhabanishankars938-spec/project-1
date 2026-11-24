from django.urls import path
from . import views, api_views
from recruitment import views_innovation

urlpatterns = [
    # Main Navigation Target: MCQ & Entrance Exam Preparation (Canonical /assessments/entrance/)
    path("", views.mcq_entrance_hub_view, name="assessments_root"),
    path("entrance/", views.mcq_entrance_hub_view, name="mcq_entrance_hub"),
    path("entrance-prep/", views.mcq_entrance_hub_view, name="entrance_prep_alias"),
    path("entrance/hub/", views.mcq_entrance_hub_view, name="entrance_root"),
    path("entrance/chapters/", views.mcq_entrance_hub_view, name="entrance_chapters"),
    path("entrance/practice/", views.question_bank_view, name="entrance_practice"),
    path("entrance/mock-test/", views.exam_list_view, name="entrance_mock_test"),
    path("entrance/results/", views.student_dashboard_view, name="entrance_results"),
    path("entrance/analytics/", views.performance_analytics_dashboard_view, name="entrance_analytics"),
    path("notes/<int:topic_id>/", views.topic_learning_notes_view, name="topic_learning_notes"),
    path("analytics/", views.performance_analytics_dashboard_view, name="performance_analytics"),
    path("api/targets/set/", views.personal_target_set_view, name="personal_target_set"),
    
    # Question Bank Explorer & Interactive Practice
    path("questions/", views.question_bank_view, name="question_bank"),
    path("questions/<int:question_id>/", views.question_detail_view, name="question_detail"),
    
    # Live Examination System & Timed Mock Tests
    path("exams/", views.exam_list_view, name="exam_list"),
    path("exams/start/<slug:exam_slug>/", views.exam_start_view, name="exam_start"),
    path("exams/live/<int:attempt_id>/", views.exam_live_view, name="exam_live"),
    path("exams/results/<int:attempt_id>/", views.exam_result_view, name="exam_result"),
    path("exams/results/<int:attempt_id>/practice-wrong/", views.practice_wrong_questions_view, name="practice_wrong_questions"),
    
    # HackerRank-Style Coding Practice
    path("coding/", views.coding_list_view, name="coding_list"),
    path("coding/<slug:problem_slug>/", views.coding_workspace_view, name="coding_workspace"),
    
    # Special Interview Learning Packages
    path("special-topics/", views.special_interview_hub_view, name="special_interview_hub"),
    path("special-topics/<slug:package_slug>/", views.special_interview_detail_view, name="special_interview_detail"),
    
    # Dashboards & Career Module
    path("dashboard/", views.student_dashboard_view, name="student_assessment_dashboard"),
    path("career-prep/", views.career_prep_view, name="career_prep"),
    
    # Admin Assessment Suite
    path("admin/hub/", views.admin_assessment_hub_view, name="admin_assessment_hub"),
    path("admin/question-bank/", views.admin_question_management_view, name="admin_question_management"),
    path("admin/attempts/reset/", views.admin_attempt_reset_view, name="admin_attempt_reset"),
    path("admin/questions/<int:question_id>/<str:action>/", views.admin_question_action_view, name="admin_question_action"),
    path("admin/questions/bulk-import/", views.admin_bulk_import_questions_view, name="admin_bulk_import_questions"),
    
    # AI Examination Coach & Adaptive Practice
    path("coach/", views_innovation.exam_coach_view, name="exam_coach_dashboard"),
    path("coach/practice/", views_innovation.exam_coach_practice_view, name="exam_coach_practice"),

    # REST / AJAX API Endpoints
    path("api/exams/<int:attempt_id>/save-answer/", api_views.api_exam_save_answer, name="api_exam_save_answer"),
    path("api/exams/<int:attempt_id>/submit/", api_views.api_exam_submit, name="api_exam_submit"),
    path("api/code/run/", api_views.api_code_run, name="api_code_run"),
    path("api/code/submit/", api_views.api_code_submit, name="api_code_submit"),
    path("api/ai/explain/", api_views.api_ai_explain, name="api_ai_explain"),
    path("api/ai/assistant/", views.ai_educational_assistant_view, name="ai_educational_assistant"),
    path("api/ai/generate-questions/", api_views.api_ai_generate_questions, name="api_ai_generate_questions"),
]

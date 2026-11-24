from django.contrib import admin
from .models import (
    Stream, Subject, Chapter, Topic, Question, QuestionOption, QuestionExplanation,
    QuestionPackage, Examination, ExamQuestion, ExamAttempt, ExamResponse,
    UserQuestionHistory, TopicCompletion,
    CodingProblem, TestCase, CodingSubmission, StudentSkillMastery,
    PlacementReadiness, CareerOpportunity, AIGenerationBatch
)


@admin.register(Stream)
class StreamAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "order", "is_active")
    list_filter = ("subject", "is_active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}



class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 4


class QuestionExplanationInline(admin.StackedInline):
    model = QuestionExplanation
    can_delete = False


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "order", "is_active", "total_questions_count")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "order")
    list_filter = ("subject",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "difficulty", "question_type", "is_pyq", "pyq_exam", "pyq_year", "status")
    list_filter = ("subject", "difficulty", "question_type", "is_pyq", "status")
    search_fields = ("title", "question_text", "pyq_source")
    inlines = [QuestionOptionInline, QuestionExplanationInline]


@admin.register(Examination)
class ExaminationAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "target_entrance_exam", "duration_minutes", "total_marks", "is_published")
    list_filter = ("category", "is_entrance_mock", "is_published")
    search_fields = ("title", "description", "target_entrance_exam")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "examination", "status", "score", "percentage", "passed", "started_at")
    list_filter = ("status", "passed")
    search_fields = ("user__username", "examination__title")


@admin.register(CodingProblem)
class CodingProblemAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "difficulty", "time_limit_seconds", "memory_limit_mb")
    list_filter = ("difficulty", "subject")
    search_fields = ("title", "description")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(CodingSubmission)
class CodingSubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "problem", "language", "status", "passed_cases_count", "total_cases_count", "execution_time_ms", "submitted_at")
    list_filter = ("status", "language")
    search_fields = ("user__username", "problem__title")


@admin.register(CareerOpportunity)
class CareerOpportunityAdmin(admin.ModelAdmin):
    list_display = ("title", "organization_name", "opportunity_type", "location", "verification_date", "is_active")
    list_filter = ("opportunity_type", "is_active")
    search_fields = ("title", "organization_name", "source_name")


admin.site.register(QuestionPackage)
admin.site.register(TestCase)
admin.site.register(StudentSkillMastery)
admin.site.register(PlacementReadiness)
admin.site.register(UserQuestionHistory)
admin.site.register(TopicCompletion)
admin.site.register(AIGenerationBatch)

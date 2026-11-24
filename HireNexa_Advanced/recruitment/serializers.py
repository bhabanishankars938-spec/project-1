from rest_framework import serializers
from accounts.models import User, AuditLog
from .models import (
    Organization, OrganizationMember, Job, Resume, ResumeExtractedData,
    Application, AIMatchResult, Interview, Notification, CandidateProfile
)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "first_name", "last_name", "date_joined"]
        read_only_fields = ["id", "date_joined"]


class OrganizationSerializer(serializers.ModelSerializer):
    job_count = serializers.IntegerField(source="jobs.count", read_only=True)
    member_count = serializers.IntegerField(source="members.count", read_only=True)

    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "description", "website", "industry", "company_size", "location", "is_active", "job_count", "member_count", "created_at"]
        read_only_fields = ["id", "slug", "created_at"]


class JobSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    applicant_count = serializers.IntegerField(source="applications.count", read_only=True)
    company_name = serializers.CharField(required=False, allow_blank=True)
    required_skills = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Job
        fields = [
            "id", "organization", "organization_name", "title", "company_name",
            "department", "job_type", "experience_level", "location",
            "workplace_type", "salary_min", "salary_max", "required_skills",
            "min_experience_years", "description", "is_active", "applicant_count", "created_at"
        ]
        read_only_fields = ["id", "organization", "created_at"]


class AIMatchResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMatchResult
        fields = ["overall_score", "skill_score", "semantic_score", "matched_skills", "missing_skills", "explanation", "recommendation", "evaluated_at"]


class ApplicationSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source="candidate.username", read_only=True)
    job_title = serializers.CharField(source="job.title", read_only=True)
    company_name = serializers.CharField(source="job.company_name", read_only=True)
    ai_result = AIMatchResultSerializer(read_only=True)

    class Meta:
        model = Application
        fields = [
            "id", "candidate", "candidate_name", "job", "job_title", "company_name",
            "status", "skill_score", "semantic_score", "final_score",
            "matched_skills", "missing_skills", "recruiter_rating", "recruiter_notes",
            "rejection_reason", "ai_result", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "final_score", "created_at", "updated_at"]


class InterviewSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source="application.candidate.username", read_only=True)
    job_title = serializers.CharField(source="application.job.title", read_only=True)

    class Meta:
        model = Interview
        fields = [
            "id", "application", "candidate_name", "job_title", "round_name",
            "scheduled_at", "mode", "meeting_link", "location", "notes",
            "status", "interviewer_feedback", "created_at"
        ]
        read_only_fields = ["id", "created_at"]


class ResumeSerializer(serializers.ModelSerializer):
    candidate_username = serializers.CharField(source="candidate.username", read_only=True)

    class Meta:
        model = Resume
        fields = ["id", "candidate", "candidate_username", "file_name", "file_size", "mime_type", "is_verified", "uploaded_at"]
        read_only_fields = ["id", "file_size", "mime_type", "is_verified", "uploaded_at"]


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "actor_username", "organization_id", "organization_name", "action", "resource_type", "resource_id", "ip_address", "details", "timestamp"]
        read_only_fields = ["id", "timestamp"]

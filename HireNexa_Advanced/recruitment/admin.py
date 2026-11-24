from django.contrib import admin
from .models import (
    CandidateProfile, RecruiterProfile, Job, Resume,
    Application, Interview, Organization, OrganizationMember,
    NewsAnnouncement, SubscriptionPlan, Payment,
    SavedJob, UserReport, CompanyVerificationDocument
)

admin.site.register(Organization)
admin.site.register(OrganizationMember)
admin.site.register(CandidateProfile)
admin.site.register(RecruiterProfile)
admin.site.register(Job)
admin.site.register(Resume)
admin.site.register(Application)
admin.site.register(Interview)
admin.site.register(NewsAnnouncement)
admin.site.register(SubscriptionPlan)
admin.site.register(Payment)
admin.site.register(SavedJob)
admin.site.register(UserReport)
admin.site.register(CompanyVerificationDocument)

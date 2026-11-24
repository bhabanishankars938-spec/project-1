from django import forms
from .models import (
    CandidateProfile, RecruiterProfile, Job, Resume, Interview,
    CandidateEducation, CandidateSkill, CandidateProject, Organization,
    NewsAnnouncement, SubscriptionPlan, ProjectPortfolio, ProjectFile
)

class CandidateProfileForm(forms.ModelForm):
    preferred_locations_input = forms.CharField(
        required=False,
        label="Preferred Work Locations",
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "e.g. Bengaluru, Hyderabad, Pune, Remote (comma-separated)",
            "id": "id_preferred_locations_input",
        }),
        help_text="Specify one or multiple preferred cities or states (e.g. Bengaluru, Bhubaneswar, Remote)"
    )

    class Meta:
        model = CandidateProfile
        fields = [
            "full_name", "headline", "phone", "education", "university",
            "graduation_year", "cgpa", "location", "preferred_work_mode", "skills",
            "github_url", "linkedin_url", "portfolio_url", "bio", "resume_consent"
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Your full legal name"}),
            "headline": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Aspiring Backend Engineer | Python & Django"}),
            "phone": forms.TextInput(attrs={"class": "form-input", "placeholder": "+91 98765 43210"}),
            "education": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. B.Tech Computer Science"}),
            "university": forms.TextInput(attrs={"class": "form-input", "placeholder": "College or University name"}),
            "graduation_year": forms.NumberInput(attrs={"class": "form-input", "placeholder": "2026"}),
            "cgpa": forms.TextInput(attrs={"class": "form-input", "placeholder": "8.5 / 10"}),
            "location": forms.TextInput(attrs={"class": "form-input", "placeholder": "City, State / Remote"}),
            "preferred_work_mode": forms.Select(attrs={"class": "form-input"}, choices=[
                ("ALL", "All Modes (Remote / Hybrid / On-site)"),
                ("REMOTE", "Remote Only"),
                ("HYBRID", "Hybrid Workplace"),
                ("ON_SITE", "On-site Office Only"),
            ]),
            "skills": forms.TextInput(attrs={"class": "form-input", "placeholder": "Python, Django, SQL, React, AWS, Docker"}),
            "github_url": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://github.com/username"}),
            "linkedin_url": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://linkedin.com/in/username"}),
            "portfolio_url": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://yourportfolio.dev"}),
            "bio": forms.Textarea(attrs={"class": "form-input", "rows": 4, "placeholder": "Share a brief summary of your projects, achievements, and career interests..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.preferred_locations:
            if isinstance(self.instance.preferred_locations, list):
                self.fields["preferred_locations_input"].initial = ", ".join(self.instance.preferred_locations)
            else:
                self.fields["preferred_locations_input"].initial = str(self.instance.preferred_locations)

    def save(self, commit=True):
        instance = super().save(commit=False)
        locs_str = self.cleaned_data.get("preferred_locations_input", "")
        if locs_str:
            instance.preferred_locations = [loc.strip() for loc in locs_str.split(",") if loc.strip()]
        else:
            instance.preferred_locations = []
        if commit:
            instance.save()
        return instance


class CandidateEducationForm(forms.ModelForm):
    class Meta:
        model = CandidateEducation
        fields = ["degree", "institution", "field_of_study", "start_year", "end_year", "grade_or_cgpa", "is_current"]
        widgets = {
            "degree": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Bachelor of Technology (B.Tech)"}),
            "institution": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. National Institute of Technology"}),
            "field_of_study": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Computer Science & Engineering"}),
            "start_year": forms.NumberInput(attrs={"class": "form-input", "placeholder": "2022"}),
            "end_year": forms.NumberInput(attrs={"class": "form-input", "placeholder": "2026"}),
            "grade_or_cgpa": forms.TextInput(attrs={"class": "form-input", "placeholder": "8.9 CGPA"}),
        }


class CandidateSkillForm(forms.ModelForm):
    class Meta:
        model = CandidateSkill
        fields = ["name", "proficiency", "years_of_experience"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Python, Docker, PostgreSQL"}),
            "proficiency": forms.Select(attrs={"class": "form-input"}),
            "years_of_experience": forms.NumberInput(attrs={"class": "form-input", "step": "0.5", "placeholder": "1.5"}),
        }


class CandidateProjectForm(forms.ModelForm):
    class Meta:
        model = CandidateProject
        fields = ["title", "technologies", "description", "repo_url", "project_url"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. AI-Powered Resume Parser"}),
            "technologies": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Python, Django, PyMuPDF, PostgreSQL"}),
            "description": forms.Textarea(attrs={"class": "form-input", "rows": 3, "placeholder": "Explain the project objective, your role, and key results achieved..."}),
            "repo_url": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://github.com/username/project"}),
            "project_url": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://demo.project.com"}),
        }


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result


class ProjectPortfolioForm(forms.ModelForm):
    project_files = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={
            "class": "form-input",
            "multiple": True,
            "id": "id_project_files",
            "accept": ".pdf,.zip,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg",
        }),
        help_text="Upload documentation, screenshots, architecture diagrams, or code zip archives (PDF, ZIP, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG — max 50 MB each)."
    )

    class Meta:
        model = ProjectPortfolio
        fields = [
            "project_name",
            "category",
            "technologies",
            "description",
            "github_url",
            "live_demo_url",
            "video_url",
        ]
        widgets = {
            "project_name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. Cloud-Native Microservices Platform",
                "required": "true",
            }),
            "category": forms.Select(attrs={
                "class": "form-input",
            }),
            "technologies": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. React, TypeScript, Django, PostgreSQL, Docker, Redis",
                "required": "true",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-input",
                "rows": 4,
                "placeholder": "Detailed architectural breakdown, system design, technical decisions, key problem solved, and production deployment notes...",
                "required": "true",
            }),
            "github_url": forms.URLInput(attrs={
                "class": "form-input",
                "placeholder": "https://github.com/username/repository",
            }),
            "live_demo_url": forms.URLInput(attrs={
                "class": "form-input",
                "placeholder": "https://live-demo.hirenexa.com",
            }),
            "video_url": forms.URLInput(attrs={
                "class": "form-input",
                "placeholder": "https://youtube.com/watch?v=... or Loom walkthrough URL",
            }),
        }


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = [
            "name", "industry", "company_size", "website", "description",
            "building_name", "unit_number", "street_address", "area", "city", "district", "state", "pin_code", "country",
            "contact_email", "contact_phone"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. TechCorp Systems"}),
            "industry": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Enterprise Cloud & AI Software"}),
            "company_size": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. 50-200 employees"}),
            "website": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://techcorp.io"}),
            "description": forms.Textarea(attrs={"class": "form-input", "rows": 3, "placeholder": "Company overview and hiring culture..."}),
            "building_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Cyber City Tower B"}),
            "unit_number": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Level 4, Suite 402"}),
            "street_address": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Magarpatta Road"}),
            "area": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Hadapsar", "id": "id_org_area"}),
            "city": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Pune", "id": "id_org_city"}),
            "district": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Pune", "id": "id_org_district"}),
            "state": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Maharashtra", "id": "id_org_state"}),
            "pin_code": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. 411028", "id": "id_org_pincode"}),
            "country": forms.TextInput(attrs={"class": "form-input", "placeholder": "India"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-input", "placeholder": "hr@techcorp.io"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-input", "placeholder": "+91 98765 43210"}),
        }


class RecruiterProfileForm(forms.ModelForm):
    class Meta:
        model = RecruiterProfile
        fields = ["company_name", "designation", "department", "phone", "industry", "company_size", "website"]
        widgets = {
            "company_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. TechCorp Systems"}),
            "designation": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Head of Talent Acquisition"}),
            "department": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Engineering Hiring"}),
            "phone": forms.TextInput(attrs={"class": "form-input", "placeholder": "+91 98765 43210"}),
            "website": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://company.io"}),
            "industry": forms.TextInput(attrs={"class": "form-input", "placeholder": "AI Software"}),
            "company_size": forms.TextInput(attrs={"class": "form-input", "placeholder": "50-200"}),
        }


class JobForm(forms.ModelForm):
    screening_questions = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-input",
            "rows": 3,
            "placeholder": "1. How many years of experience do you have with Django?\n2. Are you comfortable with hybrid work in Bengaluru?"
        }),
        required=False,
        help_text="Custom pre-screening questions (one per line or JSON array)"
    )

    class Meta:
        model = Job
        fields = [
            "title", "department", "target_course", "vacancies", "hiring_rounds",
            "job_type", "experience_level", "workplace_type", "location",
            "salary_currency", "salary_period", "salary_min", "salary_max",
            "is_salary_negotiable", "display_salary_publicly",
            "required_skills", "min_experience_years",
            "screening_questions", "is_ai_screening_enabled",
            "description", "status", "is_active"
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Senior Backend Engineer / MCA Full Stack Developer"}),
            "department": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Engineering / Cloud Infrastructure"}),
            "target_course": forms.Select(attrs={"class": "form-input"}),
            "vacancies": forms.NumberInput(attrs={"class": "form-input", "min": 1, "placeholder": "e.g. 5"}),
            "hiring_rounds": forms.TextInput(attrs={"class": "form-input", "placeholder": "Round 1 (Resume & Screening), Round 2 (Technical & Coding), Round 3 (System Design), Final (HR)"}),
            "job_type": forms.Select(attrs={"class": "form-input"}),
            "experience_level": forms.Select(attrs={"class": "form-input"}),
            "workplace_type": forms.Select(attrs={"class": "form-input"}),
            "location": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Bengaluru, Karnataka / Remote"}),
            "salary_currency": forms.Select(attrs={"class": "form-input"}),
            "salary_period": forms.Select(attrs={"class": "form-input"}),
            "salary_min": forms.NumberInput(attrs={"class": "form-input", "placeholder": "e.g. 800000"}),
            "salary_max": forms.NumberInput(attrs={"class": "form-input", "placeholder": "e.g. 1500000"}),
            "is_salary_negotiable": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "display_salary_publicly": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "required_skills": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Python, Django, PostgreSQL, Docker, AWS"}),
            "min_experience_years": forms.NumberInput(attrs={"class": "form-input", "min": 0, "placeholder": "0 for Freshers / 3 for Experienced"}),
            "screening_questions": forms.Textarea(attrs={"class": "form-input", "rows": 3, "placeholder": "1. How many years of experience do you have with Django?\n2. Are you comfortable with hybrid work in Bengaluru?"}),
            "is_ai_screening_enabled": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "status": forms.Select(attrs={"class": "form-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "description": forms.Textarea(attrs={"class": "form-input", "rows": 6, "placeholder": "Describe role responsibilities, team structure, tech stack, and benefits..."}),
        }

    def clean_screening_questions(self):
        data = self.cleaned_data.get("screening_questions")
        if isinstance(data, list):
            return data
        if isinstance(data, str):
            data_str = data.strip()
            if not data_str:
                return []
            import json
            try:
                parsed = json.loads(data_str)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
            return [line.strip() for line in data_str.splitlines() if line.strip()]
        return []

    def clean(self):
        cleaned_data = super().clean()
        s_min = cleaned_data.get("salary_min")
        s_max = cleaned_data.get("salary_max")
        if s_min is not None and s_min < 0:
            self.add_error("salary_min", "Minimum salary cannot be negative.")
        if s_max is not None and s_max < 0:
            self.add_error("salary_max", "Maximum salary cannot be negative.")
        if s_min is not None and s_max is not None and s_min > s_max:
            self.add_error("salary_max", "Maximum salary must be greater than or equal to minimum salary.")
        vacancies = cleaned_data.get("vacancies")
        if vacancies is not None and vacancies < 1:
            self.add_error("vacancies", "Vacancies count must be at least 1.")
        return cleaned_data


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "name", "slug", "tier", "price_monthly", "annual_price", "currency",
            "billing_period", "max_active_jobs", "max_hr_seats", "ai_credits_monthly",
            "max_resumes_per_month", "ai_matching_enabled", "advanced_analytics",
            "priority_support", "is_active", "is_popular", "description"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Enterprise Growth"}),
            "slug": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. enterprise-growth"}),
            "tier": forms.Select(attrs={"class": "form-input"}),
            "price_monthly": forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "placeholder": "99.00"}),
            "annual_price": forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "placeholder": "999.00"}),
            "currency": forms.TextInput(attrs={"class": "form-input", "placeholder": "USD or INR"}),
            "billing_period": forms.TextInput(attrs={"class": "form-input", "placeholder": "MONTHLY"}),
            "max_active_jobs": forms.NumberInput(attrs={"class": "form-input", "placeholder": "50"}),
            "max_hr_seats": forms.NumberInput(attrs={"class": "form-input", "placeholder": "10"}),
            "max_resumes_per_month": forms.NumberInput(attrs={"class": "form-input", "placeholder": "1000"}),
            "ai_credits_monthly": forms.NumberInput(attrs={"class": "form-input", "placeholder": "1000"}),
            "ai_matching_enabled": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "advanced_analytics": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "priority_support": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "is_popular": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "description": forms.Textarea(attrs={"class": "form-input", "rows": 3, "placeholder": "Plan summary and highlight features..."}),
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Enterprise Growth"}),
            "slug": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. enterprise-growth"}),
            "price_monthly": forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "placeholder": "99.00"}),
            "currency": forms.TextInput(attrs={"class": "form-input", "placeholder": "USD or INR"}),
            "billing_period": forms.TextInput(attrs={"class": "form-input", "placeholder": "MONTHLY"}),
            "max_active_jobs": forms.NumberInput(attrs={"class": "form-input", "placeholder": "50"}),
            "max_hr_seats": forms.NumberInput(attrs={"class": "form-input", "placeholder": "10"}),
            "ai_credits_monthly": forms.NumberInput(attrs={"class": "form-input", "placeholder": "1000"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "is_popular": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }


class RejectOrgForm(forms.Form):
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-input", "rows": 3, "placeholder": "Provide detailed feedback or documentation deficiency reason for rejection..."}),
        required=True
    )


class ResumeUploadForm(forms.ModelForm):
    class Meta:
        model = Resume
        fields = ["file"]
        widgets = {
            "file": forms.FileInput(attrs={"class": "form-input", "accept": ".pdf,.docx"})
        }

    def clean_file(self):
        f = self.cleaned_data["file"]
        allowed = (".pdf", ".docx")
        if not f.name.lower().endswith(allowed):
            raise forms.ValidationError("Upload a valid PDF or DOCX file.")
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Maximum resume size is 5 MB.")
        return f


class InterviewForm(forms.ModelForm):
    scheduled_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-input"})
    )
    provider = forms.ChoiceField(
        choices=Interview.Provider.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-input"})
    )
    duration_minutes = forms.IntegerField(
        required=False,
        initial=45,
        widget=forms.NumberInput(attrs={"class": "form-input", "placeholder": "45"})
    )
    class Meta:
        model = Interview
        fields = ["round_name", "scheduled_at", "mode", "provider", "duration_minutes", "meeting_link", "location", "notes"]
        widgets = {
            "round_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Technical Round 1: System Design & Algorithms"}),
            "mode": forms.Select(attrs={"class": "form-input"}),
            "meeting_link": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://meet.google.com/xyz-abc or Zoom URL (optional, auto-generated if blank)"}),
            "location": forms.TextInput(attrs={"class": "form-input", "placeholder": "Company Office, Bengaluru (if in-person)"}),
            "notes": forms.Textarea(attrs={"class": "form-input", "rows": 3, "placeholder": "Topics to cover, preparation guide for candidate, interviewer names..."}),
        }


class CreateHRForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. sneha_recruiter"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-input", "placeholder": "e.g. sneha@techcorp.io"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-input", "placeholder": "Temporary password"}))
    designation = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Technical Recruiter"}))
    department = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Campus Hiring"}))


class FreelancerProfileForm(forms.ModelForm):
    class Meta:
        from .models import FreelancerProfile
        model = FreelancerProfile
        fields = [
            "full_name", "headline", "hourly_rate", "experience_years",
            "skills", "portfolio_url", "github_url", "linkedin_url",
            "bio", "availability"
        ]
        widgets = {
            "headline": forms.TextInput(attrs={"placeholder": "e.g. Senior Full-Stack Engineer | Python, React & AWS", "class": "form-input"}),
            "skills": forms.TextInput(attrs={"placeholder": "e.g. Python, Django, React, TypeScript, Docker, AWS", "class": "form-input"}),
            "bio": forms.Textarea(attrs={"rows": 4, "placeholder": "Describe your background, freelance projects delivered, and specialties...", "class": "form-input"}),
            "portfolio_url": forms.URLInput(attrs={"placeholder": "https://yourportfolio.dev", "class": "form-input"}),
            "github_url": forms.URLInput(attrs={"placeholder": "https://github.com/username", "class": "form-input"}),
            "linkedin_url": forms.URLInput(attrs={"placeholder": "https://linkedin.com/in/username", "class": "form-input"}),
            "hourly_rate": forms.NumberInput(attrs={"placeholder": "50.00", "class": "form-input"}),
            "availability": forms.Select(attrs={"class": "form-input"}),
        }


class ProjectForm(forms.ModelForm):
    class Meta:
        from .models import Project
        model = Project
        fields = [
            "title", "company_name", "description", "budget_type",
            "budget_min", "budget_max", "required_skills", "duration", "is_active"
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Build REST APIs & React Dashboard", "class": "form-input"}),
            "company_name": forms.TextInput(attrs={"placeholder": "e.g. Acme Tech Studio", "class": "form-input"}),
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Detailed scope of work, deliverables, and timeline...", "class": "form-input"}),
            "required_skills": forms.TextInput(attrs={"placeholder": "e.g. Python, FastAPI, React, PostgreSQL", "class": "form-input"}),
            "budget_type": forms.Select(attrs={"class": "form-input"}),
            "budget_min": forms.NumberInput(attrs={"class": "form-input", "placeholder": "500"}),
            "budget_max": forms.NumberInput(attrs={"class": "form-input", "placeholder": "2000"}),
            "duration": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. 1-2 months"}),
        }


class ProjectProposalForm(forms.ModelForm):
    class Meta:
        from .models import ProjectProposal
        model = ProjectProposal
        fields = ["bid_amount", "estimated_days", "cover_letter"]
        widgets = {
            "bid_amount": forms.NumberInput(attrs={"placeholder": "Enter your proposed quote ($ or INR)", "class": "form-input"}),
            "estimated_days": forms.NumberInput(attrs={"placeholder": "Estimated delivery time (in days)", "class": "form-input"}),
            "cover_letter": forms.Textarea(attrs={"rows": 4, "placeholder": "Explain why you are the best fit, relevant past work, and how you will execute this project...", "class": "form-input"}),
        }


class NewsAnnouncementForm(forms.ModelForm):
    class Meta:
        model = NewsAnnouncement
        fields = [
            "title", "category", "target_audience", "priority",
            "summary", "content", "external_link", "attachment",
            "is_pinned", "is_active", "expires_at"
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Annual Campus Placement Drive 2026: Schedule & Guidelines"}),
            "category": forms.Select(attrs={"class": "form-input"}),
            "target_audience": forms.Select(attrs={"class": "form-input"}),
            "priority": forms.Select(attrs={"class": "form-input"}),
            "summary": forms.TextInput(attrs={"class": "form-input", "placeholder": "Brief 1-line overview displayed on cards and tickers..."}),
            "content": forms.Textarea(attrs={"class": "form-input", "rows": 6, "placeholder": "Full details, requirements, schedules, and instructions for candidates and recruiters..."}),
            "external_link": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://example.com/register (Optional)"}),
            "attachment": forms.FileInput(attrs={"class": "form-input", "accept": ".pdf,.png,.jpg,.jpeg,.doc,.docx"}),
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-input"}),
        }


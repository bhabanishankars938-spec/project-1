from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

# ==============================================================================
# 1. ORGANIZATIONS & MULTI-TENANCY
# ==============================================================================

class Organization(models.Model):
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(blank=True, help_text="Overview of the company, mission, and culture")
    website = models.URLField(blank=True)
    industry = models.CharField(max_length=120, blank=True, help_text="e.g. AI & Cloud Software, Fintech, EdTech")
    company_size = models.CharField(max_length=80, blank=True, help_text="e.g. 50-200 employees")
    location = models.CharField(max_length=160, blank=True, help_text="Headquarters city / country")
    logo = models.FileField(upload_to="org_logos/", blank=True, null=True)

    # Address & Location Fields
    country = models.CharField(max_length=100, blank=True, default="India", help_text="Country")
    state = models.CharField(max_length=100, blank=True, default="", help_text="State")
    district = models.CharField(max_length=100, blank=True, default="", help_text="District")
    city = models.CharField(max_length=100, blank=True, default="", help_text="City")
    area = models.CharField(max_length=120, blank=True, default="", help_text="Area / Locality / Neighborhood")
    building_name = models.CharField(max_length=150, blank=True, default="", help_text="Office / Building name")
    unit_number = models.CharField(max_length=50, blank=True, default="", help_text="Floor or unit number")
    street_address = models.CharField(max_length=200, blank=True, default="", help_text="Street address")
    pin_code = models.CharField(max_length=20, blank=True, default="", help_text="PIN / Postal Code")
    formatted_address = models.TextField(blank=True, default="", help_text="Complete structured formatted address")
    contact_email = models.EmailField(max_length=254, blank=True, default="")
    contact_phone = models.CharField(max_length=30, blank=True, default="")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    # Structured References to Verified India Location Hierarchy
    state_ref = models.ForeignKey(
        "recruitment.State",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations",
        help_text="Direct reference to verified State in India location hierarchy"
    )
    district_ref = models.ForeignKey(
        "recruitment.District",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations",
        help_text="Direct reference to verified District"
    )
    city_ref = models.ForeignKey(
        "recruitment.City",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations",
        help_text="Direct reference to verified City"
    )
    area_ref = models.ForeignKey(
        "recruitment.Area",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations",
        help_text="Direct reference to verified Area / Locality"
    )
    pincode_ref = models.ForeignKey(
        "recruitment.PinCode",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations",
        help_text="Direct reference to verified Postal PIN Code"
    )
    registered_office_address = models.CharField(max_length=255, blank=True, default="", help_text="Official registered headquarters office address")
    branch_office_address = models.CharField(max_length=255, blank=True, default="", help_text="Branch/operating office address if distinct from registered HQ")
    map_url = models.URLField(blank=True, default="", help_text="Google Maps / OpenStreetMap view URL")
    directions_url = models.URLField(blank=True, default="", help_text="Google Maps Directions URL for candidate navigation")

    @property
    def effective_registered_address(self):
        return self.registered_office_address or self.formatted_address or self.location or "Registered Headquarters"

    @property
    def effective_branch_address(self):
        return self.branch_office_address or "Same as Registered Headquarters"

    @property
    def google_maps_url(self):
        if self.map_url:
            return self.map_url
        query = self.formatted_address or f"{self.name} {self.city or ''} {self.state or ''}".strip()
        import urllib.parse
        return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}"

    @property
    def directions_link(self):
        if self.directions_url:
            return self.directions_url
        destination = self.formatted_address or f"{self.name} {self.city or ''} {self.state or ''}".strip()
        import urllib.parse
        return f"https://www.google.com/maps/dir/?api=1&destination={urllib.parse.quote(destination)}"

    @property
    def office_name(self):
        return self.building_name

    @office_name.setter
    def office_name(self, value):
        self.building_name = value

    @property
    def building(self):
        return self.building_name

    @building.setter
    def building(self, value):
        self.building_name = value

    @property
    def floor(self):
        return self.unit_number

    @floor.setter
    def floor(self, value):
        self.unit_number = value

    @property
    def street(self):
        return self.street_address

    @street.setter
    def street(self, value):
        self.street_address = value

    def generate_formatted_address(self):
        """Constructs an authoritative structured address string from physical address components."""
        parts = []
        if self.unit_number:
            parts.append(f"Floor/Unit {self.unit_number}")
        if self.building_name:
            parts.append(self.building_name)
        if self.street_address:
            parts.append(self.street_address)
        if self.area:
            parts.append(self.area)
        elif self.area_ref:
            parts.append(self.area_ref.name)
        if self.city:
            parts.append(self.city)
        elif self.city_ref:
            parts.append(self.city_ref.name)
        if self.district and self.district != self.city:
            parts.append(self.district)
        elif self.district_ref and (not self.city_ref or self.district_ref.name != self.city_ref.name):
            parts.append(self.district_ref.name)
        if self.state:
            parts.append(self.state)
        elif self.state_ref:
            parts.append(self.state_ref.name)
        if self.pin_code:
            parts.append(f"PIN: {self.pin_code}")
        elif self.pincode_ref:
            parts.append(f"PIN: {self.pincode_ref.pin_code}")
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)

    class VerificationStatus(models.TextChoices):
        APPROVED = "APPROVED", "Approved / Verified"
        PENDING = "PENDING", "Pending Verification"
        REJECTED = "REJECTED", "Rejected"

    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.APPROVED,
        help_text="Verification status evaluated by Platform Owner"
    )
    rejection_reason = models.TextField(blank=True, help_text="Reason recorded if company registration is rejected")
    is_active = models.BooleanField(default=True, help_text="Platform Owner can activate/suspend organization access")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "org"
            slug = base_slug
            counter = 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        if not self.formatted_address:
            generated = self.generate_formatted_address()
            if generated:
                self.formatted_address = generated

        if not self.location and (self.city or self.state):
            parts = [p for p in [self.city, self.state] if p]
            self.location = ", ".join(parts)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OrganizationMember(models.Model):
    class MemberRole(models.TextChoices):
        ADMIN = "ADMIN", "Company Admin"
        HR = "HR", "HR / Recruiter"
        INTERVIEWER = "INTERVIEWER", "Interviewer / Technical Reviewer"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="org_memberships")
    role = models.CharField(max_length=30, choices=MemberRole.choices, default=MemberRole.HR)
    department = models.CharField(max_length=100, blank=True)
    can_post_jobs = models.BooleanField(default=True)
    can_schedule_interviews = models.BooleanField(default=True)
    can_download_resumes = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="unique_org_user_membership")
        ]
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user.username} - {self.organization.name} ({self.role})"


class Subscription(models.Model):
    class Plan(models.TextChoices):
        STARTER = "STARTER", "Starter (Free Tier)"
        PRO = "PRO", "Pro Recruiter"
        ENTERPRISE = "ENTERPRISE", "Enterprise Scale"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        EXPIRED = "EXPIRED", "Expired"

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="subscription")
    plan_name = models.CharField(max_length=40, choices=Plan.choices, default=Plan.STARTER)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.ACTIVE)
    max_active_jobs = models.IntegerField(default=5)
    max_hr_seats = models.IntegerField(default=3)
    ai_credits_monthly = models.IntegerField(default=500)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.organization.name} - {self.plan_name} ({self.status})"


class SubscriptionPlan(models.Model):
    class PlanTier(models.TextChoices):
        FREE = "FREE", "Free / Starter"
        GROWTH = "GROWTH", "Growth"
        PRO = "PRO", "Professional"
        ENTERPRISE = "ENTERPRISE", "Enterprise"

    Tier = PlanTier

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    tier = models.CharField(max_length=30, choices=PlanTier.choices, default=PlanTier.GROWTH)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    annual_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=10, default="INR")
    billing_period = models.CharField(max_length=20, default="MONTHLY")
    max_active_jobs = models.IntegerField(default=5)
    max_hr_seats = models.IntegerField(default=3)
    ai_credits_monthly = models.IntegerField(default=500)
    max_resumes_per_month = models.IntegerField(default=500)
    ai_matching_enabled = models.BooleanField(default=True)
    advanced_analytics = models.BooleanField(default=False)
    priority_support = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    features_json = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["price_monthly"]

    @property
    def monthly_price(self):
        return self.price_monthly

    @monthly_price.setter
    def monthly_price(self, val):
        self.price_monthly = val

    @property
    def max_jobs(self):
        return self.max_active_jobs

    @max_jobs.setter
    def max_jobs(self, val):
        self.max_active_jobs = val

    @property
    def max_recruiters(self):
        return self.max_hr_seats

    @max_recruiters.setter
    def max_recruiters(self, val):
        self.max_hr_seats = val

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or "plan"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.currency} {self.price_monthly}/mo)"


class Payment(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Completed / Verified"
        PENDING = "PENDING", "Pending Verification"
        FAILED = "FAILED", "Failed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="INR")
    transaction_id = models.CharField(max_length=120, unique=True)
    provider = models.CharField(max_length=40, default="RAZORPAY")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    plan_name = models.CharField(max_length=60, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.transaction_id} - {self.currency} {self.amount} ({self.status})"



# ==============================================================================
# 2. PROFILES (RECRUITER & CANDIDATE)
# ==============================================================================

class RecruiterProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recruiter_profile")
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="recruiters")
    company_name = models.CharField(max_length=160, blank=True)
    designation = models.CharField(max_length=120, blank=True, help_text="e.g. Head of Talent Acquisition")
    department = models.CharField(max_length=120, blank=True, help_text="e.g. Engineering Hiring")
    phone = models.CharField(max_length=30, blank=True)
    company_size = models.CharField(max_length=80, blank=True, help_text="e.g. 50-200 employees")
    industry = models.CharField(max_length=120, blank=True, help_text="e.g. AI / Cloud Software")
    website = models.URLField(blank=True)

    def save(self, *args, **kwargs):
        if self.organization and not self.company_name:
            self.company_name = self.organization.name
        super().save(*args, **kwargs)

    def __str__(self):
        return self.company_name or self.user.username


class CandidateProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="candidate_profile")
    full_name = models.CharField(max_length=120, blank=True)
    headline = models.CharField(max_length=160, blank=True, help_text="e.g. Aspiring Backend Engineer | Python & Django")
    phone = models.CharField(max_length=30, blank=True)
    education = models.CharField(max_length=160, blank=True, help_text="e.g. B.Tech Computer Science")
    university = models.CharField(max_length=160, blank=True, help_text="College or University name")
    graduation_year = models.IntegerField(null=True, blank=True, help_text="Year of passing, e.g. 2026")
    cgpa = models.CharField(max_length=30, blank=True, help_text="e.g. 8.7 / 10 or 85%")
    location = models.CharField(max_length=120, blank=True)
    preferred_locations = models.JSONField(default=list, blank=True, help_text="List of preferred location strings")
    preferred_work_mode = models.CharField(max_length=40, default="ALL", blank=True, help_text="ALL, REMOTE, HYBRID, ON_SITE")
    skills = models.CharField(max_length=500, blank=True, help_text="Comma-separated skills")
    github_url = models.URLField(blank=True, help_text="https://github.com/username")
    linkedin_url = models.URLField(blank=True, help_text="https://linkedin.com/in/username")
    portfolio_url = models.URLField(blank=True, help_text="Personal website or portfolio")
    bio = models.TextField(blank=True, help_text="Professional summary or student intro")
    resume_consent = models.BooleanField(default=True, help_text="Candidate consent to share resume with verified employers")
    updated_at = models.DateTimeField(auto_now=True)

    def completion_percentage(self):
        fields = [self.full_name, self.headline, self.education, self.university, self.skills, self.github_url, self.linkedin_url, self.bio]
        filled = sum(1 for f in fields if f and str(f).strip())
        return int((filled / len(fields)) * 100)

    def __str__(self):
        return self.full_name or self.user.username


class CandidateEducation(models.Model):
    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="educations")
    degree = models.CharField(max_length=120, help_text="e.g. B.Tech Computer Science & Engineering")
    institution = models.CharField(max_length=160, help_text="University or College")
    field_of_study = models.CharField(max_length=120, blank=True)
    start_year = models.IntegerField(null=True, blank=True)
    end_year = models.IntegerField(null=True, blank=True)
    grade_or_cgpa = models.CharField(max_length=30, blank=True)
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-end_year", "-start_year"]

    def __str__(self):
        return f"{self.degree} at {self.institution}"


class CandidateSkill(models.Model):
    class Proficiency(models.TextChoices):
        BEGINNER = "BEGINNER", "Beginner"
        INTERMEDIATE = "INTERMEDIATE", "Intermediate"
        ADVANCED = "ADVANCED", "Advanced"
        EXPERT = "EXPERT", "Expert"

    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="candidate_skills")
    name = models.CharField(max_length=100)
    proficiency = models.CharField(max_length=20, choices=Proficiency.choices, default=Proficiency.INTERMEDIATE)
    years_of_experience = models.FloatField(default=0.0)
    verified = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["candidate", "name"], name="unique_candidate_skill")
        ]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.proficiency})"


class CandidateProject(models.Model):
    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    technologies = models.CharField(max_length=255, blank=True, help_text="e.g. Python, Django, PostgreSQL, Docker")
    project_url = models.URLField(blank=True, help_text="Live project demo")
    repo_url = models.URLField(blank=True, help_text="GitHub repository URL")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


# ==============================================================================
# 3. RESUMES & STRUCTURED PARSED DATA
# ==============================================================================

class Resume(models.Model):
    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resumes")
    file = models.FileField(upload_to="private_resumes/")
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.IntegerField(default=0, help_text="File size in bytes")
    file_hash = models.CharField(max_length=64, blank=True, help_text="SHA-256 integrity hash")
    mime_type = models.CharField(max_length=80, default="application/pdf")
    extracted_text = models.TextField(blank=True)
    is_verified = models.BooleanField(default=True, help_text="Passed malware and format validation")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.candidate.username} resume ({self.file_name or 'PDF'})"


class ResumeExtractedData(models.Model):
    resume = models.OneToOneField(Resume, on_delete=models.CASCADE, related_name="extracted_data")
    skills = models.JSONField(default=list, blank=True)
    education = models.JSONField(default=list, blank=True)
    experience = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)
    raw_text = models.TextField(blank=True)
    extracted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Parsed data for {self.resume}"


# ==============================================================================
# 4. JOBS & REQUIREMENTS
# ==============================================================================

class Job(models.Model):
    class JobType(models.TextChoices):
        FULL_TIME = "Full-time", "Full-time"
        PART_TIME = "Part-time", "Part-time"
        INTERNSHIP = "Internship", "Internship"
        CONTRACT = "Contract", "Contract"

    class ExperienceLevel(models.TextChoices):
        ENTRY = "Entry Level", "Entry Level / College Graduate"
        MID = "Mid Level", "Mid Level (1-3 yrs)"
        SENIOR = "Senior", "Senior (3-6 yrs)"
        LEAD = "Lead", "Lead / Principal (6+ yrs)"

    class WorkplaceType(models.TextChoices):
        REMOTE = "Remote", "Remote"
        HYBRID = "Hybrid", "Hybrid"
        ONSITE = "On-site", "On-site"

    class TargetCourse(models.TextChoices):
        ALL = "ALL", "All Courses / Open to All"
        MCA = "MCA", "MCA (Master of Computer Applications)"
        MBA = "MBA", "MBA (Master of Business Administration)"
        BTECH = "BTECH", "B.Tech / B.E."
        BCA = "BCA", "BCA / Computer Applications"
        BBA = "BBA", "BBA / Management"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active / Open"
        PAUSED = "PAUSED", "Paused / On Hold"
        FILLED = "FILLED", "Filled / Target Reached"
        CLOSED = "CLOSED", "Closed / Archived"

    class SalaryCurrency(models.TextChoices):
        INR = "INR", "INR (Indian Rupee)"
        USD = "USD", "USD (US Dollar)"
        EUR = "EUR", "EUR (Euro)"
        GBP = "GBP", "GBP (British Pound)"

    class SalaryPeriod(models.TextChoices):
        MONTHLY = "MONTHLY", "per month"
        ANNUAL = "ANNUAL", "per annum"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name="jobs")
    recruiter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posted_jobs")
    title = models.CharField(max_length=160)
    company_name = models.CharField(max_length=160)
    department = models.CharField(max_length=120, blank=True, help_text="e.g. MCA / IT, MBA / Management, Engineering, HR, Finance")
    target_course = models.CharField(max_length=40, choices=TargetCourse.choices, default=TargetCourse.ALL, help_text="Target academic degree/department (e.g. MCA, MBA)")
    vacancies = models.PositiveIntegerField(default=5, help_text="Total openings/hiring target count for this role")
    hiring_rounds = models.CharField(
        max_length=300,
        default="1st Round (Screening & Aptitude), 2nd Round (Technical / GD), 3rd Round (Interview), Final Round (HR)",
        help_text="Configured stages from 1st round to last round"
    )
    job_type = models.CharField(max_length=40, choices=JobType.choices, default=JobType.FULL_TIME)
    experience_level = models.CharField(max_length=40, choices=ExperienceLevel.choices, default=ExperienceLevel.ENTRY)
    salary_currency = models.CharField(max_length=10, choices=SalaryCurrency.choices, default=SalaryCurrency.INR)
    salary_period = models.CharField(max_length=20, choices=SalaryPeriod.choices, default=SalaryPeriod.ANNUAL)
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_salary_negotiable = models.BooleanField(default=False)
    display_salary_publicly = models.BooleanField(default=True)
    screening_questions = models.JSONField(default=list, blank=True)
    is_ai_screening_enabled = models.BooleanField(default=True)
    location = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=100, blank=True, default="India")
    state = models.CharField(max_length=100, blank=True, db_index=True, default="", help_text="State")
    district = models.CharField(max_length=100, blank=True, db_index=True, default="", help_text="District")
    city = models.CharField(max_length=100, blank=True, db_index=True, default="", help_text="City for structured search")
    area = models.CharField(max_length=120, blank=True, db_index=True, default="", help_text="Area / Locality")
    pin_code = models.CharField(max_length=20, blank=True, default="")
    office_address = models.CharField(max_length=255, blank=True, default="", help_text="Office street address")
    workplace_type = models.CharField(max_length=40, choices=WorkplaceType.choices, default=WorkplaceType.REMOTE)
    description = models.TextField()
    required_skills = models.CharField(max_length=700, help_text="Comma-separated, e.g. Python, Django, SQL, Docker")
    min_experience_years = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    is_featured = models.BooleanField(default=False, help_text="Featured on homepage by Platform Owner")
    is_active = models.BooleanField(default=True)
    deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def skill_list(self):
        return [s.strip().lower() for s in self.required_skills.split(",") if s.strip()]

    def hiring_rounds_list(self):
        if not self.hiring_rounds:
            return ["1st Round (Screening)", "2nd Round (Technical/GD)", "Final Round (HR)"]
        return [r.strip() for r in self.hiring_rounds.split(",") if r.strip()]

    @property
    def hired_count(self):
        return self.applications.filter(status=Application.Status.HIRED).count()

    @property
    def remaining_vacancies(self):
        return max(0, self.vacancies - self.hired_count)

    @property
    def hiring_progress_percentage(self):
        if self.vacancies <= 0:
            return 0
        return min(100, int((self.hired_count / self.vacancies) * 100))

    def get_round_funnel_counts(self):
        """Returns candidate counts from 1st round to last round and hired."""
        apps = self.applications.all()
        return {
            "applied": apps.filter(status=Application.Status.APPLIED).count(),
            "screening": apps.filter(status=Application.Status.SCREENING).count(),
            "round_1": apps.filter(status=Application.Status.ROUND_1).count(),
            "round_2": apps.filter(status=Application.Status.ROUND_2).count(),
            "round_3": apps.filter(status=Application.Status.ROUND_3).count(),
            "final_round": apps.filter(status=Application.Status.FINAL_ROUND).count(),
            "shortlisted": apps.filter(status=Application.Status.SHORTLISTED).count(),
            "interview": apps.filter(status=Application.Status.INTERVIEW).count(),
            "offer": apps.filter(status=Application.Status.OFFER).count(),
            "hired": apps.filter(status=Application.Status.HIRED).count(),
            "rejected": apps.filter(status=Application.Status.REJECTED).count(),
            "total": apps.count(),
        }

    def save(self, *args, **kwargs):
        if self.organization and not self.company_name:
            self.company_name = self.organization.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} @ {self.company_name}"


class JobRequirement(models.Model):
    class Importance(models.TextChoices):
        CRITICAL = "CRITICAL", "Must-have (Core Requirement)"
        PREFERRED = "PREFERRED", "Good-to-have (Bonus)"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="requirements")
    skill_name = models.CharField(max_length=100)
    importance = models.CharField(max_length=20, choices=Importance.choices, default=Importance.CRITICAL)
    min_years = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.skill_name} ({self.importance}) for {self.job.title}"


# ==============================================================================
# 5. APPLICATIONS, AI MATCHING & SHORTLISTING
# ==============================================================================

class Application(models.Model):
    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        SCREENING = "SCREENING", "Screening"
        ROUND_1 = "ROUND_1", "1st Round (Screening / Aptitude)"
        ROUND_2 = "ROUND_2", "2nd Round (Technical / GD)"
        ROUND_3 = "ROUND_3", "3rd Round (Interview / Presentation)"
        FINAL_ROUND = "FINAL_ROUND", "Final Round (HR & Leadership)"
        SHORTLISTED = "SHORTLISTED", "Shortlisted"
        INTERVIEW = "INTERVIEW", "Interview Scheduled"
        OFFER = "OFFER", "Offer Extended"
        HIRED = "HIRED", "Hired / Selected"
        REJECTED = "REJECTED", "Rejected"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    resume = models.ForeignKey(Resume, on_delete=models.PROTECT)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.APPLIED)
    rejection_reason = models.TextField(blank=True, help_text="Audit-logged reason if candidate application is rejected")
    recruiter_rating = models.IntegerField(default=0, help_text="Rating 1-5")
    recruiter_notes = models.TextField(blank=True, help_text="Internal notes for hiring team")
    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    skill_score = models.FloatField(default=0)
    semantic_score = models.FloatField(null=True, blank=True)
    final_score = models.FloatField(default=0)
    explanation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_hired(self):
        return self.status == self.Status.HIRED

    @property
    def round_label(self):
        round_map = {
            self.Status.APPLIED: "Applied",
            self.Status.SCREENING: "Screening",
            self.Status.ROUND_1: "1st Round",
            self.Status.ROUND_2: "2nd Round",
            self.Status.ROUND_3: "3rd Round",
            self.Status.FINAL_ROUND: "Final HR Round",
            self.Status.SHORTLISTED: "Shortlisted",
            self.Status.INTERVIEW: "Interview Scheduled",
            self.Status.OFFER: "Offer Extended",
            self.Status.HIRED: "Hired 🎉",
            self.Status.REJECTED: "Rejected",
            self.Status.WITHDRAWN: "Withdrawn",
        }
        return round_map.get(self.status, self.get_status_display())

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["candidate", "job"], name="unique_candidate_job_application")
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.candidate.username} - {self.job.title} ({self.status})"


class AIMatchResult(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name="ai_result")
    overall_score = models.FloatField(default=0)
    skill_score = models.FloatField(default=0)
    semantic_score = models.FloatField(default=0)
    experience_score = models.FloatField(default=0)
    education_score = models.FloatField(default=0)
    matched_skills = models.JSONField(default=list)
    missing_skills = models.JSONField(default=list)
    explanation = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI Result {self.overall_score}% for {self.application}"


class ShortlistedCandidate(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="shortlisted_candidates")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="shortlisted_entries")
    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shortlisted_by_orgs")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="shortlist_records")
    shortlisted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="shortlists_made")
    notes = models.TextField(blank=True)
    shortlisted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "candidate"], name="unique_job_candidate_shortlist")
        ]
        ordering = ["-shortlisted_at"]

    def __str__(self):
        return f"{self.candidate.username} shortlisted for {self.job.title}"


# ==============================================================================
# 6. INTERVIEWS, NOTIFICATIONS & AUDIT LOGS
# ==============================================================================

class Interview(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        RESCHEDULED = "RESCHEDULED", "Rescheduled"

    class Mode(models.TextChoices):
        ONLINE = "ONLINE", "Online Video Call"
        IN_PERSON = "IN_PERSON", "In-person Interview"
        PHONE = "PHONE", "Phone Interview"

    class Provider(models.TextChoices):
        INTERNAL = "INTERNAL", "HireNexa Virtual Room"
        ZOOM = "ZOOM", "Zoom Video Meetings"
        GOOGLE_MEET = "GOOGLE_MEET", "Google Meet"
        TEAMS = "TEAMS", "Microsoft Teams"
        IN_PERSON = "IN_PERSON", "In-Person Office"
        PHONE = "PHONE", "Phone Call"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="interviews")
    round_name = models.CharField(max_length=120, default="Technical Round 1")
    scheduled_at = models.DateTimeField()
    mode = models.CharField(max_length=40, choices=Mode.choices, default=Mode.ONLINE)
    provider = models.CharField(max_length=30, choices=Provider.choices, default=Provider.INTERNAL)
    meeting_id = models.CharField(max_length=100, blank=True, default="", help_text="Meeting / Room ID")
    meeting_password = models.CharField(max_length=100, blank=True, default="", help_text="Passcode / PIN for interview")
    duration_minutes = models.PositiveIntegerField(default=45, help_text="Scheduled duration in minutes")
    meeting_metadata = models.JSONField(default=dict, blank=True, help_text="Raw provider payload/metadata")
    meeting_link = models.URLField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SCHEDULED)
    interviewer_feedback = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"Interview: {self.round_name} - {self.application.candidate.username} ({self.status})"

    @property
    def is_zoom(self):
        return self.provider == self.Provider.ZOOM

    @property
    def is_internal(self):
        return self.provider == self.Provider.INTERNAL

    @property
    def join_url(self):
        if self.meeting_link:
            return self.meeting_link
        from django.urls import reverse
        try:
            return reverse("recruitment:interview_room", args=[self.pk])
        except Exception:
            return f"/interviews/{self.pk}/room/"


class Notification(models.Model):
    class Type(models.TextChoices):
        APPLICATION = "APPLICATION", "Application Update"
        INTERVIEW = "INTERVIEW", "Interview Invitation"
        SYSTEM = "SYSTEM", "System Notice"
        STATUS_UPDATE = "STATUS_UPDATE", "Status Change"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_notifications")
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=40, choices=Type.choices, default=Type.SYSTEM)
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification to {self.recipient.username}: {self.title}"


from accounts.models import AuditLog


class ConsentRecord(models.Model):
    class ConsentType(models.TextChoices):
        RESUME_SHARING = "RESUME_SHARING", "Resume Sharing with Verified Employers"
        DATA_PROCESSING = "DATA_PROCESSING", "Automated AI Profiling & Processing"
        COMMUNICATION = "COMMUNICATION", "Job Alerts & Recruiter Communications"

    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents")
    consent_type = models.CharField(max_length=50, choices=ConsentType.choices)
    is_granted = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-granted_at"]

    def __str__(self):
        status = "Granted" if self.is_granted else "Revoked"
        return f"{self.candidate.username} - {self.consent_type} ({status})"


# ==============================================================================
# 7. FREELANCE HUB & PROJECT GIGS
# ==============================================================================

class FreelancerProfile(models.Model):
    class Availability(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available for Projects"
        PART_TIME = "PART_TIME", "Part-Time Projects Only"
        BUSY = "BUSY", "Currently Booked"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="freelancer_profile")
    full_name = models.CharField(max_length=120, blank=True)
    headline = models.CharField(max_length=160, blank=True, help_text="e.g. Senior Full-Stack Engineer | Python, React & Cloud")
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Hourly billing rate")
    experience_years = models.IntegerField(default=0, help_text="Years of professional freelance experience")
    skills = models.CharField(max_length=500, blank=True, help_text="Comma-separated skills, e.g. Python, Django, React, AWS")
    portfolio_url = models.URLField(blank=True, help_text="Personal website or portfolio link")
    github_url = models.URLField(blank=True, help_text="https://github.com/username")
    linkedin_url = models.URLField(blank=True, help_text="https://linkedin.com/in/username")
    bio = models.TextField(blank=True, help_text="Freelancer summary, technical specialties, and past deliverables")
    availability = models.CharField(max_length=30, choices=Availability.choices, default=Availability.AVAILABLE)
    resume = models.ForeignKey(Resume, null=True, blank=True, on_delete=models.SET_NULL, related_name="freelancer_resumes")
    updated_at = models.DateTimeField(auto_now=True)

    def completion_percentage(self):
        fields = [self.full_name, self.headline, self.skills, self.portfolio_url, self.bio]
        filled = sum(1 for f in fields if f and str(f).strip())
        return int((filled / len(fields)) * 100)

    def skill_list(self):
        return [s.strip() for s in self.skills.split(",") if s.strip()]

    def __str__(self):
        return self.full_name or self.user.username


class Project(models.Model):
    class BudgetType(models.TextChoices):
        FIXED = "FIXED", "Fixed Price"
        HOURLY = "HOURLY", "Hourly Rate"

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posted_projects")
    title = models.CharField(max_length=180)
    company_name = models.CharField(max_length=160, blank=True)
    description = models.TextField()
    budget_type = models.CharField(max_length=20, choices=BudgetType.choices, default=BudgetType.FIXED)
    budget_min = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    budget_max = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    required_skills = models.CharField(max_length=500, help_text="Comma-separated skills")
    duration = models.CharField(max_length=80, default="1-3 months")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def skill_list(self):
        return [s.strip() for s in self.required_skills.split(",") if s.strip()]

    def __str__(self):
        return self.title


class ProjectProposal(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="proposals")
    freelancer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_proposals")
    cover_letter = models.TextField()
    bid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_days = models.IntegerField(default=14)
    resume = models.ForeignKey(Resume, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    client_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["project", "freelancer"], name="unique_project_freelancer_proposal")
        ]

    def __str__(self):
        return f"Proposal by {self.freelancer.username} for {self.project.title}"


# ==============================================================================
# 8. NEWS & ANNOUNCEMENTS BROADCAST ENGINE
# ==============================================================================

class NewsAnnouncement(models.Model):
    class Category(models.TextChoices):
        NOTICE = "NOTICE", "Official Notice / Circular"
        PLACEMENT_DRIVE = "PLACEMENT_DRIVE", "Campus Placement Drive"
        EXAM_UPDATE = "EXAM_UPDATE", "Assessment / Interview Schedule"
        COMPANY_NEWS = "COMPANY_NEWS", "Company Announcement"
        SYSTEM = "SYSTEM", "Platform Announcement"

    class TargetAudience(models.TextChoices):
        ALL = "ALL", "All Users & Public"
        CANDIDATES = "CANDIDATES", "Candidates / Students Only"
        RECRUITERS = "RECRUITERS", "HR & Recruiters Only"
        COMPANIES = "COMPANIES", "Company Administrators Only"

    class Priority(models.TextChoices):
        NORMAL = "NORMAL", "Standard"
        HIGH = "HIGH", "High Priority"
        URGENT = "URGENT", "Urgent / Breaking Alert"

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="authored_announcements")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="news_announcements",
        help_text="Null for platform-wide author announcements"
    )
    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=240, unique=True, blank=True)
    category = models.CharField(max_length=40, choices=Category.choices, default=Category.NOTICE)
    target_audience = models.CharField(max_length=40, choices=TargetAudience.choices, default=TargetAudience.ALL)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    summary = models.CharField(max_length=320, help_text="Brief 1-2 sentence preview")
    content = models.TextField(help_text="Detailed announcement body or guidelines")
    external_link = models.URLField(blank=True, help_text="Optional external registration or info link")
    attachment = models.FileField(upload_to="announcements/", blank=True, null=True)
    is_pinned = models.BooleanField(default=False, help_text="Pin to top of news board")
    is_active = models.BooleanField(default=True, help_text="Active / Visible")
    views_count = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-published_at"]
        verbose_name = "News & Announcement"
        verbose_name_plural = "News & Announcements"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "announcement"
            slug = base_slug
            counter = 1
            while NewsAnnouncement.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return bool(self.expires_at and timezone.now() > self.expires_at)

    def is_visible_to(self, user):
        if not self.is_active or self.is_expired:
            if user and user.is_authenticated and (getattr(user, "is_owner", False) or user.is_superuser or self.author == user):
                return True
            return False
        if self.target_audience == self.TargetAudience.ALL:
            return True
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_owner", False) or user.is_superuser or self.author == user:
            return True
        if self.organization and getattr(user, "is_company_admin", False):
            if user.org_memberships.filter(organization=self.organization).exists():
                return True
        if self.target_audience == self.TargetAudience.CANDIDATES and getattr(user, "is_candidate", False):
            return True
        if self.target_audience == self.TargetAudience.RECRUITERS and (getattr(user, "is_recruiter", False) or getattr(user, "is_company_admin", False)):
            return True
        if self.target_audience == self.TargetAudience.COMPANIES and getattr(user, "is_company_admin", False):
            return True
        return False

    def __str__(self):
        prefix = f"[{self.organization.name}] " if self.organization else "[Platform] "
        return f"{prefix}{self.title}"


# ==============================================================================
# 9. SAVED JOBS, MODERATION REPORTS & COMPANY VERIFICATION DOCUMENTS
# ==============================================================================

class SavedJob(models.Model):
    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_jobs")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="saved_by_users")
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["candidate", "job"], name="unique_candidate_saved_job")
        ]
        ordering = ["-saved_at"]

    def __str__(self):
        return f"{self.candidate.username} saved {self.job.title}"


class UserReport(models.Model):
    class ReportType(models.TextChoices):
        JOB_LISTING = "JOB_LISTING", "Suspicious Job Listing"
        PROJECT = "PROJECT", "Suspicious Freelance Project"
        SPAM = "SPAM", "Spam / Misleading Content"
        USER = "USER", "User Conduct Violation"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        INVESTIGATING = "INVESTIGATING", "Investigating"
        RESOLVED = "RESOLVED", "Resolved / Action Taken"
        DISMISSED = "DISMISSED", "Dismissed / No Violation"

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="filed_reports")
    report_type = models.CharField(max_length=40, choices=ReportType.choices, default=ReportType.JOB_LISTING)
    target_id = models.CharField(max_length=100)
    target_title = models.CharField(max_length=200, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report #{self.id} ({self.get_report_type_display()}): {self.target_title or self.target_id}"


class CompanyVerificationDocument(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="verification_documents")
    document_type = models.CharField(max_length=120, help_text="e.g. Certificate of Incorporation, GSTIN, Company PAN")
    file = models.FileField(upload_to="company_verification_docs/")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    review_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.organization.name} - {self.document_type} ({self.status})"


# ==============================================================================
# 9. INDIA LOCATION MANAGEMENT (PostgreSQL Hierarchical Tables)
# ==============================================================================

class Country(models.Model):
    name = models.CharField(max_length=100, unique=True, default="India")
    iso2 = models.CharField(max_length=2, unique=True, default="IN")
    iso3 = models.CharField(max_length=3, default="IND")
    phone_code = models.CharField(max_length=10, default="+91")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "countries"
        ordering = ["name"]

    def __str__(self):
        return self.name


class State(models.Model):
    class Type(models.TextChoices):
        STATE = "state", "State"
        UNION_TERRITORY = "union_territory", "Union Territory"

    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="states", db_column="country_id")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10)
    type = models.CharField(max_length=30, choices=Type.choices, default=Type.STATE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "states"
        ordering = ["name"]
        unique_together = [("country", "name")]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class District(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="districts", db_column="state_id")
    name = models.CharField(max_length=120)
    headquarters = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "districts"
        ordering = ["name"]
        unique_together = [("state", "name")]
        indexes = [
            models.Index(fields=["state", "name"]),
        ]

    def __str__(self):
        return f"{self.name}, {self.state.code}"


class City(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="cities", db_column="state_id")
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True, related_name="cities", db_column="district_id")
    name = models.CharField(max_length=120)
    is_metro = models.BooleanField(default=False)
    tier = models.IntegerField(default=2, choices=[(1, "Tier 1 (Metro)"), (2, "Tier 2"), (3, "Tier 3")])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cities"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["state", "name"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_metro"]),
        ]

    def __str__(self):
        return f"{self.name}, {self.state.code}"


class Area(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="areas", db_column="city_id")
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "areas"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["city", "name"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.name}, {self.city.name}"


class PinCode(models.Model):
    pin_code = models.CharField(max_length=10, db_index=True)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="pin_codes", db_column="state_id")
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True, related_name="pin_codes", db_column="district_id")
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name="pin_codes", db_column="city_id")
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True, related_name="pin_codes", db_column="area_id")
    office_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pin_codes"
        ordering = ["pin_code"]
        indexes = [
            models.Index(fields=["pin_code"]),
            models.Index(fields=["state", "pin_code"]),
        ]

    def __str__(self):
        city_or_state = self.city.name if self.city else self.state.name
        return f"{self.pin_code} - {self.office_name or city_or_state}"


# ==============================================================================
# 10. SUPABASE CANDIDATE PROJECT PORTFOLIO & FILES (PostgreSQL RLS Protected)
# ==============================================================================

class ProjectPortfolio(models.Model):
    class Category(models.TextChoices):
        WEB = "Web Development", "Web Development"
        MOBILE = "Mobile App", "Mobile App"
        AI_ML = "AI / Machine Learning", "AI / Machine Learning"
        CLOUD_DEVOPS = "Cloud / DevOps", "Cloud / DevOps"
        DATA_SCIENCE = "Data Science", "Data Science"
        BLOCKCHAIN = "Blockchain & Web3", "Blockchain & Web3"
        SYSTEMS = "Systems & Embedded", "Systems & Embedded"
        CYBERSECURITY = "Cybersecurity", "Cybersecurity"
        OTHER = "Other / Research", "Other / Research"

    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolios",
        db_column="candidate_id"
    )
    project_name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=100, choices=Category.choices, default=Category.WEB)
    technologies = models.CharField(max_length=500, help_text="Comma-separated technologies, e.g. React, Django, PostgreSQL, Docker")
    github_url = models.URLField(blank=True, default="", help_text="GitHub repository URL")
    live_demo_url = models.URLField(blank=True, default="", help_text="Live hosted application URL")
    video_url = models.URLField(blank=True, default="", help_text="Demo video or walkthrough URL (YouTube, Loom, etc.)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "project_portfolio"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["candidate", "-created_at"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self):
        return f"{self.project_name} ({self.candidate.username})"

    def get_technologies_list(self):
        if not self.technologies:
            return []
        return [t.strip() for t in self.technologies.split(",") if t.strip()]

    def preview_image(self):
        """Returns the first image attachment if available."""
        return self.files.filter(
            models.Q(file_type__startswith="image/") |
            models.Q(file_name__iendswith=".png") |
            models.Q(file_name__iendswith=".jpg") |
            models.Q(file_name__iendswith=".jpeg")
        ).first()

    def documents(self):
        """Returns non-image documents (PDF, DOCX, ZIP, PPTX)."""
        return self.files.exclude(
            models.Q(file_type__startswith="image/") |
            models.Q(file_name__iendswith=".png") |
            models.Q(file_name__iendswith=".jpg") |
            models.Q(file_name__iendswith=".jpeg")
        )

    def files_count(self):
        return self.files.count()


class ProjectFile(models.Model):
    project = models.ForeignKey(
        ProjectPortfolio,
        on_delete=models.CASCADE,
        related_name="files",
        db_column="project_id"
    )
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolio_files",
        db_column="candidate_id"
    )
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, help_text="Supabase Storage path within candidate-projects bucket")
    file_type = models.CharField(max_length=100)
    file_size = models.BigIntegerField(help_text="File size in bytes")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "project_files"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["project"]),
            models.Index(fields=["candidate"]),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.project.project_name})"

    @property
    def is_image(self):
        ft = (self.file_type or "").lower()
        fn = (self.file_name or "").lower()
        return ft.startswith("image/") or fn.endswith((".png", ".jpg", ".jpeg"))

    @property
    def is_pdf(self):
        ft = (self.file_type or "").lower()
        fn = (self.file_name or "").lower()
        return "pdf" in ft or fn.endswith(".pdf")

    @property
    def is_zip(self):
        ft = (self.file_type or "").lower()
        fn = (self.file_name or "").lower()
        return "zip" in ft or fn.endswith(".zip")

    @property
    def is_doc(self):
        fn = (self.file_name or "").lower()
        return fn.endswith((".doc", ".docx"))

    @property
    def is_presentation(self):
        fn = (self.file_name or "").lower()
        return fn.endswith((".ppt", ".pptx"))

    @property
    def formatted_size(self):
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def get_signed_download_url(self, expires_in=3600):
        from core.supabase_service import supabase_service, CANDIDATE_PROJECTS_BUCKET
        return supabase_service.create_signed_url(CANDIDATE_PROJECTS_BUCKET, self.file_path, expires_in=expires_in)




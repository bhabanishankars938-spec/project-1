import json
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


import hashlib
import json
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class EntranceTrack(models.Model):
    """
    Independent entrance examination track (e.g. MCA Entrance vs MBA Entrance).
    Each track maintains its own subjects, topics, syllabus, question bank, and targets.
    """
    class Code(models.TextChoices):
        MCA = "MCA", "MCA Entrance Preparation"
        MBA = "MBA", "MBA Entrance Preparation"
        PLACEMENT = "PLACEMENT", "Placement and Interview Prep"

    code = models.CharField(max_length=30, choices=Code.choices, unique=True)
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    target_exams = models.JSONField(default=list, help_text="e.g. ['NIMCET', 'OJEE MCA', 'CUET-PG'] or ['CAT', 'MAT', 'CMAT', 'XAT']")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Stream(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Subject(models.Model):
    class Category(models.TextChoices):
        PROGRAMMING = "PROGRAMMING", "Programming Languages"
        CORE_CS = "CORE_CS", "Core Computer Science"
        WEB_DEV = "WEB_DEV", "Web Development & Frameworks"
        AI_ML = "AI_ML", "AI & Machine Learning"
        APTITUDE = "APTITUDE", "Aptitude & Logical Reasoning"
        INTERVIEW = "INTERVIEW", "Interview Preparation"
        MATHEMATICS = "MATHEMATICS", "Mathematics"
        GENERAL_ENGLISH = "GENERAL_ENGLISH", "General English & Verbal"
        MANAGEMENT = "MANAGEMENT", "Business & Management"

    stream = models.ForeignKey(Stream, on_delete=models.SET_NULL, null=True, blank=True, related_name="subjects")
    entrance_track = models.ForeignKey(EntranceTrack, on_delete=models.SET_NULL, null=True, blank=True, related_name="subjects")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.PROGRAMMING)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default="code", help_text="Icon identifier e.g. code, database, cpu, etc.")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def total_questions_count(self):
        return self.questions.filter(status=Question.Status.APPROVED).count()

    @property
    def total_topics(self):
        return self.topics.count()

    @property
    def total_topics_count(self):
        return self.topics.count()

    @property
    def verified_questions_count(self):
        return self.questions.filter(status=Question.Status.APPROVED, is_verified=True).count()


class Topic(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="topics")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["subject", "order", "name"]
        unique_together = ("subject", "slug")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject.name} - {self.name}"

    @property
    def questions_count(self):
        return self.questions.filter(status=Question.Status.APPROVED).count()

    @property
    def verified_questions_count(self):
        return self.questions.filter(status=Question.Status.APPROVED, is_verified=True).count()


class Subtopic(models.Model):
    """Specific conceptual subtopic under a primary subject topic."""
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="subtopics")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    learning_objective = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["topic", "order", "name"]
        unique_together = ("topic", "slug")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.topic.name} > {self.name}"


class SyllabusVersion(models.Model):
    """Tracks entrance examination syllabus versions and topic mapping."""
    track = models.ForeignKey(EntranceTrack, on_delete=models.CASCADE, related_name="syllabus_versions")
    version_label = models.CharField(max_length=60, default="2026.1")
    exam_name = models.CharField(max_length=80, help_text="e.g. NIMCET, CAT, OJEE MCA, CUET-PG")
    syllabus_data = models.JSONField(default=dict)
    is_current = models.BooleanField(default=True)
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return f"{self.exam_name} Syllabus v{self.version_label}"


class LearningNote(models.Model):
    """
    Topic-wise comprehensive educational and conceptual revision notes.
    Contains Concept Understanding, Examples, Visual Comparison Tables,
    Formulas, Practice Problems, and Detailed Answers.
    """
    topic = models.OneToOneField(Topic, on_delete=models.CASCADE, related_name="learning_note")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="learning_notes")
    concept_summary = models.TextField(help_text="Introduction & core definition")
    detailed_explanation = models.TextField(help_text="Detailed concepts, types, working principles")
    real_world_applications = models.TextField(blank=True)
    advantages_disadvantages = models.TextField(blank=True)
    comparison_table_markdown = models.TextField(blank=True, help_text="Markdown comparison table of related concepts")
    common_pitfalls = models.TextField(blank=True, help_text="Common candidate mistakes & misconceptions")
    examples_json = models.JSONField(default=list, help_text="Beginner, intermediate, advanced step-by-step examples")
    quick_revision_formulas = models.JSONField(default=list, help_text="Formulas, short notes, exam high-yield points")
    practice_questions_json = models.JSONField(default=list, help_text="Curated practice problems with full explanations")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["subject", "topic"]

    def __str__(self):
        return f"Learning Notes: {self.topic.name}"


class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="chapters")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["subject", "order", "name"]
        unique_together = ("subject", "slug")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject.name} - {self.name}"


class Question(models.Model):
    class Type(models.TextChoices):
        MCQ = "MCQ", "Multiple Choice (Single Answer)"
        MSQ = "MSQ", "Multiple Select Questions"
        TRUE_FALSE = "TRUE_FALSE", "True or False"
        FILL_BLANKS = "FILL_BLANKS", "Fill in the Blanks"
        SHORT_ANSWER = "SHORT_ANSWER", "Short Answer"
        DESCRIPTIVE = "DESCRIPTIVE", "Descriptive Question"
        OUTPUT_PREDICTION = "OUTPUT_PREDICTION", "Output Prediction"
        FIND_ERROR = "FIND_ERROR", "Find the Error"
        DEBUGGING = "DEBUGGING", "Debugging Problem"
        CODING = "CODING", "Coding Problem"
        LOGICAL_REASONING = "LOGICAL_REASONING", "Logical Reasoning"
        SQL_QUERY = "SQL_QUERY", "SQL Query"

    class Level(models.TextChoices):
        BEGINNER = "BEGINNER", "Beginner Level"
        INTERMEDIATE = "INTERMEDIATE", "Intermediate Level"
        ADVANCED = "ADVANCED", "Advanced Level"
        INTERVIEW = "INTERVIEW", "Interview Level"
        PLACEMENT = "PLACEMENT", "Company Placement Level"
        EASY = "EASY", "Easy"
        MEDIUM = "MEDIUM", "Medium"
        HARD = "HARD", "Hard"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        AI_GENERATED = "AI_GENERATED", "AI Generated (Pending Review)"
        APPROVED = "APPROVED", "Verified & Approved"
        REJECTED = "REJECTED", "Rejected"

    class ReviewStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        VALIDATION = "VALIDATION", "Automated Validation Passed"
        EXPERT_REVIEW = "EXPERT_REVIEW", "Expert Review In Progress"
        VERIFIED = "VERIFIED", "Syllabus Verified"
        PUBLISHED = "PUBLISHED", "Published to Exam Bank"

    class SourceType(models.TextChoices):
        CONCEPTUAL = "CONCEPTUAL", "Conceptual MCQ"
        APPLICATION = "APPLICATION", "Application-Based MCQ"
        NUMERICAL = "NUMERICAL", "Numerical Problem"
        LOGICAL = "LOGICAL", "Logical Reasoning"
        SCENARIO = "SCENARIO", "Scenario-Based Problem"
        CODE_OUTPUT = "CODE_OUTPUT", "Code Output Prediction"
        ASSERTION_REASONING = "ASSERTION_REASONING", "Assertion & Reasoning"
        DATA_INTERPRETATION = "DATA_INTERPRETATION", "Data Interpretation"

    class QuestionOrigin(models.TextChoices):
        AUTHENTIC_PYQ = "AUTHENTIC_PYQ", "Authentic Previous Year Question (PYQ)"
        EXPERT_CURATED = "EXPERT_CURATED", "Expert Curated & Syllabus Verified"
        AI_PRACTICE = "AI_PRACTICE", "AI Practice & Concept Reinforcement"

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="questions")
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions")
    subtopic = models.ForeignKey(Subtopic, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions")
    chapter = models.ForeignKey(Chapter, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions")
    exam = models.ForeignKey(
        "Examination",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="questions",
        help_text="The specific examination this question belongs to."
    )
    order = models.PositiveIntegerField(default=1)
    question_type = models.CharField(max_length=30, choices=Type.choices, default=Type.MCQ)
    difficulty = models.CharField(max_length=20, choices=Level.choices, default=Level.BEGINNER)
    source_type = models.CharField(max_length=30, choices=SourceType.choices, default=SourceType.CONCEPTUAL)
    title = models.CharField(max_length=255, help_text="Short headline summary of question")
    question_text = models.TextField(help_text="Full question prompt with markdown support")
    code_snippet = models.TextField(blank=True, help_text="Code snippet or query associated with the question")
    language = models.CharField(max_length=40, blank=True, help_text="Programming language if applicable e.g. python, sql, cpp")
    explanation = models.TextField(blank=True, help_text="Concise 2-3 line verified explanation")
    
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("1.00"))
    negative_marks = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.25"))
    
    # Normalized unique fingerprint for duplicate detection
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True, help_text="SHA-256 normalized question fingerprint")
    concept_identifier = models.CharField(max_length=120, blank=True, default="", db_index=True, help_text="Concept identifier or tag to enforce diversity")
    version = models.PositiveIntegerField(default=1, help_text="Version number of question revision")
    verification_date = models.DateTimeField(null=True, blank=True)
    
    # Textual or JSON verified answer for non-MCQ formats
    verified_answer_key = models.TextField(blank=True, help_text="Exact string or pattern for Fill in blanks, SQL, Output, etc.")
    tags = models.JSONField(default=list, blank=True, help_text="Keywords and placement tags")
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPROVED)
    review_status = models.CharField(max_length=25, choices=ReviewStatus.choices, default=ReviewStatus.PUBLISHED)
    is_verified = models.BooleanField(default=True, help_text="True if question passes syllabus and key verification")
    verification_certainty = models.DecimalField(max_digits=4, decimal_places=2, default=1.00, help_text="0.00 to 1.00 verification certainty")
    reviewer_notes = models.TextField(blank=True)
    
    # Previous Year Questions (PYQ) Verification Metadata
    is_pyq = models.BooleanField(default=False, help_text="True if this is a verified previous year entrance exam question")
    origin = models.CharField(max_length=30, choices=QuestionOrigin.choices, default=QuestionOrigin.EXPERT_CURATED, db_index=True)
    pyq_exam = models.CharField(max_length=60, blank=True, help_text="e.g. NIMCET, OJEE, CUET-PG, CAT, MAT")
    pyq_year = models.PositiveIntegerField(null=True, blank=True, help_text="e.g. 2023, 2022")
    pyq_source = models.CharField(max_length=160, blank=True, help_text="Verified source authority and official paper citation")
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_questions")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_questions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["subject", "difficulty", "status"]),
            models.Index(fields=["question_type", "status"]),
            models.Index(fields=["fingerprint"]),
            models.Index(fields=["topic", "difficulty", "status"]),
        ]

    def compute_fingerprint(self) -> str:
        """Computes a deterministic SHA-256 fingerprint from normalized text and options."""
        clean_text = " ".join((self.question_text or "").strip().lower().split())
        payload = f"{clean_text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        if not self.fingerprint and self.question_text:
            self.fingerprint = self.compute_fingerprint()
        if self.is_pyq and self.origin != self.QuestionOrigin.AUTHENTIC_PYQ:
            self.origin = self.QuestionOrigin.AUTHENTIC_PYQ
        elif self.status == self.Status.AI_GENERATED and self.origin != self.QuestionOrigin.AI_PRACTICE:
            self.origin = self.QuestionOrigin.AI_PRACTICE
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.subject.name} - {self.get_difficulty_display()}] {self.title}"

    @property
    def year(self):
        return self.pyq_year

    @property
    def exam_name(self):
        return self.pyq_exam or (self.exam.title if self.exam else "")

    @property
    def source_reference(self):
        return self.pyq_source or ""

    @property
    def question_origin(self):
        return self.origin

    @property
    def origin_label(self):
        return self.get_origin_display()

    @property
    def origin_badge(self):
        if self.is_pyq or self.origin == self.QuestionOrigin.AUTHENTIC_PYQ:
            exam_label = self.pyq_exam or "Official PYQ"
            year_label = f" {self.pyq_year}" if self.pyq_year else ""
            return f"Authentic PYQ · {exam_label}{year_label}"
        elif self.origin == self.QuestionOrigin.AI_PRACTICE:
            return "AI Practice Problem"
        return "Expert Verified"

    @property
    def concept_id(self):
        return self.concept_identifier

    @concept_id.setter
    def concept_id(self, val):
        self.concept_identifier = val or ""

    @property
    def reviewer(self):
        return self.approved_by

    @property
    def text(self):
        return self.question_text

    @text.setter
    def text(self, val):
        self.question_text = val

    @property
    def correct_options(self):
        return self.options.filter(is_correct=True)

    @property
    def has_options(self):
        return self.question_type in [
            self.Type.MCQ, self.Type.MSQ, self.Type.TRUE_FALSE,
            self.Type.OUTPUT_PREDICTION, self.Type.FIND_ERROR,
            self.Type.LOGICAL_REASONING
        ] and self.options.exists()

    def validate_options(self):
        """Validates that this question has exactly 4 options and exactly 1 correct option."""
        opts = list(self.options.all())
        if len(opts) != 4:
            raise ValidationError(f"Question must have exactly 4 options (found {len(opts)}).")
        correct_count = sum(1 for o in opts if o.is_correct)
        if correct_count != 1:
            raise ValidationError(f"Question must have exactly 1 correct option (found {correct_count}).")

    def clean(self):
        super().clean()
        if self.pk and self.options.exists():
            self.validate_options()


class QuestionOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    option_key = models.CharField(max_length=10, help_text="Option label, e.g. A, B, C, D")
    option_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    explanation = models.TextField(blank=True, help_text="Specific reason why this choice is correct or incorrect")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "option_key"]

    @property
    def concept_id(self):
        return self.concept_identifier

    @concept_id.setter
    def concept_id(self, val):
        self.concept_identifier = val or ""

    @property
    def reviewer(self):
        return self.approved_by

    @property
    def text(self):
        return self.option_text

    @text.setter
    def text(self, val):
        self.option_text = val

    def clean(self):
        super().clean()
        if self.question_id and self.is_correct:
            existing = QuestionOption.objects.filter(question_id=self.question_id, is_correct=True).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError("A question cannot have more than one correct option.")

    def __str__(self):
        prefix = "✓" if self.is_correct else "✗"
        return f"{prefix} [{self.option_key}] {self.option_text[:60]}"


class QuestionExplanation(models.Model):
    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name="explanation_detail")
    correct_answer_summary = models.CharField(max_length=255)
    why_correct = models.TextField(help_text="Detailed reasoning why the correct answer is valid")
    why_others_incorrect = models.TextField(blank=True, help_text="Breakdown of misconceptions in other choices")
    step_by_step_logic = models.TextField(help_text="Step-by-step procedural logic")
    practical_example = models.TextField(blank=True, help_text="Real-world practical implementation example")
    programming_logic = models.TextField(blank=True, help_text="Underlying algorithmic or syntax logic")
    related_concepts = models.JSONField(default=list, blank=True)
    recommended_practice_topics = models.JSONField(default=list, blank=True)
    time_complexity = models.CharField(max_length=60, blank=True)
    space_complexity = models.CharField(max_length=60, blank=True)
    concept_note = models.TextField(blank=True, default="", help_text="Fundamental concept behind the question")
    common_mistake_warning = models.TextField(blank=True, default="", help_text="Common candidate mistake warning")
    exam_tip = models.TextField(blank=True, default="", help_text="Practical shortcut or exam tip")

    @property
    def solving_logic(self):
        return self.step_by_step_logic

    @solving_logic.setter
    def solving_logic(self, val):
        self.step_by_step_logic = val or ""

    def __str__(self):
        return f"Explanation for: {self.question.title}"


class QuestionPackage(models.Model):
    class Category(models.TextChoices):
        SPECIAL_INTERVIEW = "SPECIAL_INTERVIEW", "Special Interview Package"
        COMPANY_PLACEMENT = "COMPANY_PLACEMENT", "Company Placement Drive"
        ROLE_SPECIFIC = "ROLE_SPECIFIC", "Role Specific Preparation"
        CRASH_COURSE = "CRASH_COURSE", "Rapid Revision Course"

    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.SPECIAL_INTERVIEW)
    description = models.TextField()
    icon = models.CharField(max_length=50, default="book-open")
    badge_label = models.CharField(max_length=60, default="High Frequency")
    questions = models.ManyToManyField(Question, related_name="packages", blank=True)
    is_featured = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "title"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Examination(models.Model):
    class Kind(models.TextChoices):
        TOPIC_TEST = "topic_test", "Topic Test"
        CHAPTER_TEST = "chapter_test", "Chapter Test"
        SUBJECT_TEST = "subject_test", "Subject Test"
        MOCK_TEST = "mock_test", "Mock Test"

    class Category(models.TextChoices):
        PRACTICE = "PRACTICE", "Practice Test"
        DAILY = "DAILY", "Daily Test"
        WEEKLY = "WEEKLY", "Weekly Test"
        MONTHLY = "MONTHLY", "Monthly Test"
        MOCK_FINAL = "MOCK_FINAL", "Final Mock Test"
        PLACEMENT_MOCK = "PLACEMENT_MOCK", "Placement Mock Test"
        LIVE_TEST = "LIVE_TEST", "Custom Live Test"

    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.TOPIC_TEST)
    stream = models.ForeignKey(Stream, on_delete=models.SET_NULL, null=True, blank=True, related_name="examinations")
    entrance_track = models.ForeignKey(EntranceTrack, on_delete=models.SET_NULL, null=True, blank=True, related_name="examinations")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="examinations")
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="examinations")
    chapter = models.ForeignKey(Chapter, on_delete=models.SET_NULL, null=True, blank=True, related_name="examinations")
    is_final_combined = models.BooleanField(default=False, help_text="True if this is the comprehensive final exam unlocked after all topics completed")
    required_topics_count = models.PositiveIntegerField(default=0, help_text="Number of required completed topics to unlock")
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.PRACTICE)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    
    duration_minutes = models.PositiveIntegerField(default=17)
    max_attempts = models.PositiveIntegerField(default=5)
    total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("16.00"))
    passing_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("40.00"))
    negative_marking = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.25"), help_text="Fraction deducted for wrong answers, e.g. 0.25")
    
    shuffle_questions = models.BooleanField(default=True)
    shuffle_options = models.BooleanField(default=True)
    show_instant_results = models.BooleanField(default=True)
    is_published = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    # Entrance Examination Classification
    target_entrance_exam = models.CharField(max_length=60, blank=True, help_text="e.g. MCA Entrance, OJEE, NIMCET, CUET-PG")
    is_entrance_mock = models.BooleanField(default=False)
    pyq_year = models.PositiveIntegerField(null=True, blank=True, help_text="Specific PYQ paper year if applicable")
    
    start_window = models.DateTimeField(null=True, blank=True, help_text="Start time for live scheduled exams")
    end_window = models.DateTimeField(null=True, blank=True, help_text="End time for live scheduled exams")
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "exam"
            slug = base
            cnt = 1
            while Examination.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{cnt}"
                cnt += 1
            self.slug = slug
        if self.pk and self.questions.exists():
            self.total_marks = sum(q.marks for q in self.questions.all())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"

    @property
    def questions_count(self):
        return self.questions.filter(status=Question.Status.APPROVED).count() or self.exam_questions.count()

    @property
    def negative_marking_rate(self):
        return self.negative_marking

    @negative_marking_rate.setter
    def negative_marking_rate(self, value):
        self.negative_marking = value

    @property
    def total_computed_marks(self):
        computed = sum(q.marks for q in self.questions.filter(status=Question.Status.APPROVED))
        if computed > 0:
            return computed
        eq_computed = sum(float(eq.marks_allocated) for eq in self.exam_questions.all())
        return eq_computed if eq_computed > 0 else (self.total_marks or Decimal("16.00"))


class ExamQuestion(models.Model):
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="exam_questions")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="exam_instances")
    order = models.PositiveIntegerField(default=0)
    custom_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        unique_together = ("examination", "question")

    def __str__(self):
        return f"{self.examination.title} - Q{self.order}: {self.question.title}"

    @property
    def marks_allocated(self):
        return self.custom_marks if self.custom_marks is not None else self.question.marks


class ExamAttempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        SUBMITTED = "SUBMITTED", "Submitted"
        EXPIRED = "EXPIRED", "Auto-Submitted (Time Expired)"
        TIMED_OUT = "TIMED_OUT", "Auto-Submitted (Time Expired)"
        ABANDONED = "ABANDONED", "Abandoned"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_attempts")
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="attempts")
    attempt_number = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    
    started_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    
    score = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    total_possible_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    passed = models.BooleanField(default=False)
    
    total_questions = models.PositiveIntegerField(default=0)
    answered_count = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    incorrect_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    
    ordered_question_ids = models.JSONField(default=list, help_text="Deterministic question ordering for this candidate")
    random_seed = models.CharField(max_length=64, blank=True)
    last_active_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "examination", "attempt_number"],
                name="unique_user_exam_attempt_number"
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.examination.title} (#{self.attempt_number}) ({self.status}) [{self.score} pts]"

    @property
    def exam(self):
        return self.examination

    @exam.setter
    def exam(self, val):
        self.examination = val

    @property
    def attempted_questions(self):
        return self.answered_count

    @property
    def maximum_score(self):
        if self.total_possible_marks and self.total_possible_marks > 0:
            return self.total_possible_marks
        if self.examination and self.examination.total_marks and self.examination.total_marks > 0:
            return self.examination.total_marks
        return Decimal("16.00")

    @property
    def submission_timestamp(self):
        return self.submitted_at or self.last_active_at or self.started_at

    @property
    def is_expired(self):
        dl = self.deadline or self.expires_at
        return bool(dl and timezone.now() > dl)

    @property
    def seconds_remaining(self):
        if self.status != self.Status.IN_PROGRESS:
            return 0
        dl = self.deadline or self.expires_at
        if not dl:
            return 0
        diff = (dl - timezone.now()).total_seconds()
        return max(0, int(diff))

    def save(self, *args, **kwargs):
        if self.deadline and not self.expires_at:
            self.expires_at = self.deadline
        elif self.expires_at and not self.deadline:
            self.deadline = self.expires_at
        super().save(*args, **kwargs)


class ExamResponse(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="responses")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    
    selected_option_ids = models.JSONField(default=list, blank=True, help_text="List of option IDs selected by user")
    text_answer = models.TextField(blank=True, help_text="Text answer for fill in blanks, SQL, code, descriptive")
    
    is_marked_for_review = models.BooleanField(default=False)
    is_correct = models.BooleanField(null=True, blank=True)
    marks_awarded = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"Response to Q{self.question_id} in Attempt {self.attempt_id}"


class UserQuestionHistory(models.Model):
    """Tracks questions shown to a user across attempts to ensure fresh, unseen questions."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="question_histories")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="user_histories")
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="question_histories")
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="question_histories")
    attempt_number = models.PositiveIntegerField(default=1)
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "question", "examination", "attempt_number"],
                name="unique_user_question_exam_attempt"
            )
        ]

    def __str__(self):
        return f"{self.user.username} - Q{self.question_id} (Exam {self.examination_id}, Attempt {self.attempt_number})"


class TopicCompletion(models.Model):
    """Tracks candidate completion status and best score for each topic to govern unlock gates."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="topic_completions")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="user_completions")
    is_completed = models.BooleanField(default=False)
    best_score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    completed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "topic")
        ordering = ["-completed_at"]

    def __str__(self):
        status = "Completed" if self.is_completed else "Incomplete"
        return f"{self.user.username} - {self.topic.name}: {status} (Best: {self.best_score})"


class AttemptQuestion(models.Model):
    """Stores exact frozen snapshot of questions and randomized options per candidate attempt."""
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="attempt_questions")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="attempt_instances")
    question_order = models.PositiveIntegerField(default=1)
    shuffled_option_ids = models.JSONField(default=list, help_text="Exact shuffled option IDs for this candidate attempt")
    marks_weight = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("1.00"))
    negative_weight = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.25"))

    class Meta:
        ordering = ["question_order", "id"]
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"Attempt #{self.attempt.id} - Q{self.question_order} (Question #{self.question_id})"


class Result(models.Model):
    """
    Comprehensive percentage-based examination performance record.
    Preserves exact positive marks, negative deductions, accuracy %, completion %, and time utilization.
    """
    class Level(models.TextChoices):
        EXCELLENT = "EXCELLENT", "Excellent (90–100%)"
        VERY_GOOD = "VERY_GOOD", "Very Good (80–89.99%)"
        GOOD = "GOOD", "Good (70–79.99%)"
        AVERAGE = "AVERAGE", "Average (60–69.99%)"
        NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT", "Needs Improvement (40–59.99%)"
        PRACTICE = "PRACTICE", "Requires More Practice (Below 40%)"

    attempt = models.OneToOneField(ExamAttempt, on_delete=models.CASCADE, related_name="result_record")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_results")
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="results")
    
    total_questions = models.PositiveIntegerField(default=16)
    attempted_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    incorrect_answers = models.PositiveIntegerField(default=0)
    skipped_answers = models.PositiveIntegerField(default=0)
    
    positive_marks = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    negative_marks = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    final_score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    maximum_score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("16.00"))
    
    score_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    accuracy_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    completion_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    time_utilization_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    
    performance_level = models.CharField(max_length=30, choices=Level.choices, default=Level.PRACTICE)
    is_passed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Result #{self.id}: {self.user.username} - {self.examination.title} ({self.final_score}/{self.maximum_score} | {self.score_percentage}%)"


class TopicProgress(models.Model):
    """Tracks candidate performance across all 5 topic attempts with improvement analytics."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="topic_progress_records")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="user_progress_records")
    attempts_count = models.PositiveIntegerField(default=0)
    best_score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    best_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    latest_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    average_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    mastery_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    attempt_history = models.JSONField(default=list, help_text="List of attempts with scores and percentages")
    is_completed = models.BooleanField(default=False)
    last_attempted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "topic")
        ordering = ["topic__order", "topic__name"]

    def __str__(self):
        return f"{self.user.username} - {self.topic.name} ({self.mastery_percentage}% mastery, {self.attempts_count}/5 attempts)"


class SubjectProgress(models.Model):
    """Tracks candidate subject mastery, syllabus completion, and aggregate accuracy."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subject_progress_records")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="user_progress_records")
    total_topics_count = models.PositiveIntegerField(default=0)
    completed_topics_count = models.PositiveIntegerField(default=0)
    mastery_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    learning_progress_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "subject")
        ordering = ["subject__order", "subject__name"]

    def __str__(self):
        return f"{self.user.username} - {self.subject.name} ({self.completed_topics_count}/{self.total_topics_count} topics, {self.mastery_percentage}%)"


class PersonalTarget(models.Model):
    """Custom candidate target percentage with gap analysis and recommended practice."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="personal_targets")
    track = models.ForeignKey(EntranceTrack, on_delete=models.CASCADE, null=True, blank=True, related_name="user_targets")
    target_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("80.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "track")

    def __str__(self):
        track_name = self.track.name if self.track else "General"
        return f"{self.user.username} Target: {self.target_percentage}% ({track_name})"


class AdminReviewHistory(models.Model):
    """Audit trail for question creation, verification, and editorial workflow."""
    class Action(models.TextChoices):
        DRAFT_CREATED = "DRAFT_CREATED", "Draft Created"
        VALIDATED = "VALIDATED", "Automated Validation Passed"
        EXPERT_REVIEWED = "EXPERT_REVIEWED", "Expert Review In Progress"
        VERIFIED = "VERIFIED", "Syllabus Verified"
        PUBLISHED = "PUBLISHED", "Published to Live Exam Bank"
        REJECTED = "REJECTED", "Rejected"

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="review_history")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=30, choices=Action.choices)
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"Q#{self.question_id} - {self.action} by {self.reviewer} at {self.timestamp}"


class CodingProblem(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "EASY", "Easy"
        MEDIUM = "MEDIUM", "Medium"
        HARD = "HARD", "Hard"
        EXPERT = "EXPERT", "Expert / Placement"

    title = models.CharField(max_length=220, unique=True)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="coding_problems")
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.EASY)
    
    description = models.TextField(help_text="Problem statement with markdown support")
    input_format = models.TextField(help_text="Detailed format of input data")
    output_format = models.TextField(help_text="Detailed format of expected output")
    constraints = models.TextField(help_text="e.g. 1 <= N <= 10^5")
    
    allowed_languages = models.JSONField(default=list, help_text="['python', 'javascript', 'c', 'cpp', 'java']")
    time_limit_seconds = models.DecimalField(max_digits=4, decimal_places=2, default=2.00)
    memory_limit_mb = models.PositiveIntegerField(default=128)
    
    starter_templates = models.JSONField(default=dict, help_text="dict of language -> initial starter snippet")
    solution_code = models.TextField(blank=True, help_text="Verified reference solution")
    solution_explanation = models.TextField(blank=True, help_text="Algorithmic walkthrough and complexity analysis")
    
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["difficulty", "title"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if not self.allowed_languages:
            self.allowed_languages = ["python", "javascript", "c", "cpp", "java"]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.get_difficulty_display()}] {self.title}"


class TestCase(models.Model):
    problem = models.ForeignKey(CodingProblem, on_delete=models.CASCADE, related_name="test_cases")
    input_data = models.TextField()
    expected_output = models.TextField()
    is_hidden = models.BooleanField(default=False, help_text="True = hidden test case; False = sample test case")
    explanation = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    weight = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)

    class Meta:
        ordering = ["is_hidden", "order", "id"]

    def __str__(self):
        kind = "Hidden" if self.is_hidden else "Sample"
        return f"{kind} Test Case for {self.problem.title} (#{self.id})"


class CodingSubmission(models.Model):
    class Status(models.TextChoices):
        ACCEPTED = "ACCEPTED", "Accepted"
        WRONG_ANSWER = "WRONG_ANSWER", "Wrong Answer"
        TIME_LIMIT = "TIME_LIMIT_EXCEEDED", "Time Limit Exceeded"
        COMPILE_ERROR = "COMPILATION_ERROR", "Compilation Error"
        RUNTIME_ERROR = "RUNTIME_ERROR", "Runtime Error"
        PENDING = "PENDING", "Pending Execution"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coding_submissions")
    problem = models.ForeignKey(CodingProblem, on_delete=models.CASCADE, related_name="submissions")
    language = models.CharField(max_length=30)
    code = models.TextField()
    
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    passed_cases_count = models.PositiveIntegerField(default=0)
    total_cases_count = models.PositiveIntegerField(default=0)
    execution_time_ms = models.FloatField(default=0.0)
    memory_used_kb = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True)
    
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.user.username} - {self.problem.title} ({self.status}) [{self.passed_cases_count}/{self.total_cases_count}]"


class StudentSkillMastery(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="skill_masteries")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    
    attempted_count = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    coding_solved_count = models.PositiveIntegerField(default=0)
    accuracy_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    weak_topics = models.JSONField(default=list, blank=True)
    strong_topics = models.JSONField(default=list, blank=True)
    topic_breakdown = models.JSONField(default=dict, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "subject")

    def __str__(self):
        return f"{self.user.username} - {self.subject.name} ({self.accuracy_percentage}%)"


class PlacementReadiness(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="placement_readiness")
    overall_readiness_score = models.PositiveIntegerField(default=0, help_text="0-100 composite score")
    
    coding_score = models.PositiveIntegerField(default=0)
    mcq_score = models.PositiveIntegerField(default=0)
    core_cs_score = models.PositiveIntegerField(default=0)
    soft_skills_score = models.PositiveIntegerField(default=0)
    
    strengths = models.JSONField(default=list, blank=True)
    weaknesses = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    target_role = models.CharField(max_length=100, default="Full Stack Software Engineer")
    last_evaluated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Readiness: {self.overall_readiness_score}%"


class CareerOpportunity(models.Model):
    class Type(models.TextChoices):
        INTERNSHIP = "INTERNSHIP", "Internship Opportunity"
        TRAINING = "TRAINING", "Upcoming Training Program"
        PLACEMENT_DRIVE = "PLACEMENT_DRIVE", "Campus / Off-Campus Placement"
        HACKATHON = "HACKATHON", "Coding Contest & Hackathon"

    opportunity_type = models.CharField(max_length=30, choices=Type.choices, default=Type.INTERNSHIP)
    title = models.CharField(max_length=200)
    organization_name = models.CharField(max_length=160)
    location = models.CharField(max_length=150, default="Remote / Pan-India")
    stipend_or_perk = models.CharField(max_length=120, blank=True, help_text="e.g. ₹25,000 / month or Free Certified Training")
    
    source_name = models.CharField(max_length=120, help_text="Official verified source e.g. HireNexa Verified Portal")
    source_url = models.URLField(help_text="Direct link or application route")
    verification_date = models.DateField(default=timezone.now)
    application_deadline = models.DateField(null=True, blank=True)
    
    requirements = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-verification_date", "-created_at"]

    def __str__(self):
        return f"[{self.get_opportunity_type_display()}] {self.title} at {self.organization_name}"


class AIGenerationBatch(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    difficulty = models.CharField(max_length=20)
    question_type = models.CharField(max_length=30)
    requested_count = models.PositiveIntegerField(default=5)
    generated_count = models.PositiveIntegerField(default=0)
    approved_count = models.PositiveIntegerField(default=0)
    
    raw_prompt = models.TextField(blank=True)
    raw_response = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Batch #{self.id}: {self.subject.name} ({self.generated_count} Qs)"


# Aliases for domain readability and consistency
Exam = Examination
Option = QuestionOption
Attempt = ExamAttempt
ExaminationAttempt = ExamAttempt
CandidateAnswer = ExamResponse
QuestionExposureHistory = UserQuestionHistory


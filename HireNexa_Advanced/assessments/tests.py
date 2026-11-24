import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from assessments.models import (
    Subject, Topic, Chapter, Question, QuestionOption, QuestionExplanation,
    Examination, ExamQuestion, ExamAttempt, ExamResponse,
    UserQuestionHistory, TopicCompletion,
    CodingProblem, TestCase as CodingTestCase, CodingSubmission,
    StudentSkillMastery, PlacementReadiness,
    EntranceTrack, LearningNote, Result, TopicProgress, PersonalTarget
)
from assessments.sandbox import SecureExecutionSandbox, evaluate_submission_against_problem, sanitize_and_validate_code
from assessments.services import ExamEvaluationService, QuestionRepetitionEngine, QuestionBankShortageError


class AssessmentSystemTests(TestCase):
    """
    Automated test suite verifying Question Bank, Entrance Exam Hub,
    Live Exam Scoring, Auto-Save, Negative Marking, and Coding Execution Sandbox.
    """

    def setUp(self):
        self.client = Client()

        # Create test student
        self.student = User.objects.create_user(
            username="student_tester",
            email="student_tester@hirenexa.internal",
            password="StudentPassword123!",
            role=User.Role.CANDIDATE,
            is_active=True,
            is_email_verified=True,
        )

        # Create test owner
        self.owner = User.objects.create_user(
            username="owner_tester",
            email="owner_tester@hirenexa.internal",
            password="OwnerPassword123!",
            role=User.Role.OWNER,
            is_superuser=True,
            is_staff=True,
            is_active=True,
            is_email_verified=True,
        )

        # Subject & Topic
        self.subject = Subject.objects.create(
            name="C Programming",
            slug="c-programming",
            category=Subject.Category.PROGRAMMING,
            order=1
        )
        self.topic = Topic.objects.create(
            subject=self.subject,
            name="Pointers",
            slug="pointers"
        )

        # Question 1: 4 Options MCQ
        self.q1 = Question.objects.create(
            subject=self.subject,
            topic=self.topic,
            title="Pointer Dereference",
            question_text="What is *ptr if ptr points to an int with value 42?",
            question_type=Question.Type.MCQ,
            difficulty=Question.Level.BEGINNER,
            marks=Decimal("1.00"),
            negative_marks=Decimal("0.25"),
            is_pyq=True,
            pyq_exam="NIMCET",
            pyq_year=2023,
            pyq_source="NIMCET Official Paper",
            status=Question.Status.APPROVED,
        )
        self.opt1_a = QuestionOption.objects.create(question=self.q1, option_key="A", option_text="42", is_correct=True)
        self.opt1_b = QuestionOption.objects.create(question=self.q1, option_key="B", option_text="Address", is_correct=False)
        self.opt1_c = QuestionOption.objects.create(question=self.q1, option_key="C", option_text="NULL", is_correct=False)
        self.opt1_d = QuestionOption.objects.create(question=self.q1, option_key="D", option_text="0", is_correct=False)

        QuestionExplanation.objects.create(
            question=self.q1,
            correct_answer_summary="Option A (42)",
            why_correct="Dereference operator retrieves the value at memory address.",
            why_others_incorrect="B gives address if un-dereferenced.",
            step_by_step_logic="Step 1: Identify ptr.\nStep 2: Dereference yields 42.",
        )

        # Question 2: Another MCQ for testing negative marking
        self.q2 = Question.objects.create(
            subject=self.subject,
            topic=self.topic,
            title="Array Decay",
            question_text="In C, an array name decays into what?",
            question_type=Question.Type.MCQ,
            difficulty=Question.Level.BEGINNER,
            marks=Decimal("1.00"),
            negative_marks=Decimal("0.25"),
            status=Question.Status.APPROVED,
        )
        self.opt2_a = QuestionOption.objects.create(question=self.q2, option_key="A", option_text="Pointer to first element", is_correct=True)
        self.opt2_b = QuestionOption.objects.create(question=self.q2, option_key="B", option_text="Integer value", is_correct=False)
        self.opt2_c = QuestionOption.objects.create(question=self.q2, option_key="C", option_text="Structure", is_correct=False)
        self.opt2_d = QuestionOption.objects.create(question=self.q2, option_key="D", option_text="Null pointer", is_correct=False)

        # Examination
        self.exam = Examination.objects.create(
            title="C Programming Timed Mock Test",
            slug="c-programming-timed-mock-test",
            category=Examination.Category.PRACTICE,
            target_entrance_exam="NIMCET",
            is_entrance_mock=True,
            duration_minutes=30,
            total_marks=Decimal("2.00"),
            passing_percentage=Decimal("50.00"),
            negative_marking_rate=Decimal("0.25"),
            is_published=True,
        )
        ExamQuestion.objects.create(examination=self.exam, question=self.q1, order=1, custom_marks=1.0)
        ExamQuestion.objects.create(examination=self.exam, question=self.q2, order=2, custom_marks=1.0)

        # Coding Problem
        self.prob = CodingProblem.objects.create(
            title="Sum of Two Numbers",
            slug="sum-of-two-numbers",
            subject=self.subject,
            difficulty=CodingProblem.Difficulty.EASY,
            description="Given two integers A and B, print their sum.",
            input_format="A and B separated by space",
            output_format="Sum of A and B",
            time_limit_seconds=Decimal("2.00"),
            starter_templates={
                "python": "import sys\nlines = sys.stdin.read().split()\nif lines: print(int(lines[0]) + int(lines[1]))\n",
                "javascript": r"const fs = require('fs'); const [a, b] = fs.readFileSync(0, 'utf-8').trim().split(/\s+/).map(Number); console.log(a + b);" + "\n"
            }
        )
        CodingTestCase.objects.create(problem=self.prob, input_data="5 10", expected_output="15", is_hidden=False, order=1)
        CodingTestCase.objects.create(problem=self.prob, input_data="-3 7", expected_output="4", is_hidden=True, order=2)

    # --------------------------------------------------------------------------
    # 1. ENTRANCE PREP & QUESTION BANK VIEW TESTS
    # --------------------------------------------------------------------------

    def test_mcq_entrance_hub_page_loads(self):
        """Entrance Exam hub renders 200 with subjects, questions, and mock tests."""
        response = self.client.get(reverse("mcq_entrance_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MCQ & Entrance Exam Preparation")
        self.assertContains(response, "C Programming")

    def test_mcq_entrance_hub_exam_filtering(self):
        """Filter questions by specific entrance exam e.g. NIMCET."""
        response = self.client.get(reverse("mcq_entrance_hub") + "?exam=nimcet")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pointer Dereference")

    def test_question_detail_interactive_view(self):
        """Question detail displays question statement, 4 options, and explanation."""
        response = self.client.get(reverse("question_detail", kwargs={"question_id": self.q1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pointer Dereference")
        self.assertContains(response, "Option A")
        self.assertContains(response, "42")

    # --------------------------------------------------------------------------
    # 2. LIVE EXAMINATION & SCORING SERVICE TESTS
    # --------------------------------------------------------------------------

    def test_exam_start_and_attempt_creation(self):
        """Starting an exam creates an ExamAttempt with synchronized countdown."""
        self.client.force_login(self.student)
        response = self.client.post(reverse("exam_start", kwargs={"exam_slug": self.exam.slug}), follow=True)
        self.assertEqual(response.status_code, 200)

        attempt = ExamAttempt.objects.filter(user=self.student, examination=self.exam).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.status, ExamAttempt.Status.IN_PROGRESS)
        self.assertGreater(attempt.seconds_remaining, 0)
        self.assertEqual(attempt.total_questions, 2)

    def test_exam_save_answer_ajax(self):
        """Auto-save saves option selection and marks for review via AJAX."""
        self.client.force_login(self.student)
        attempt, _ = ExamEvaluationService.start_or_resume_attempt(self.student, self.exam)

        save_url = reverse("api_exam_save_answer", kwargs={"attempt_id": attempt.id})
        payload = {
            "question_id": self.q1.id,
            "selected_option_ids": [self.opt1_a.id],
            "is_marked_for_review": True,
            "time_spent_seconds": 15
        }
        response = self.client.post(save_url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["is_marked_for_review"])

        resp = ExamResponse.objects.get(attempt=attempt, question=self.q1)
        self.assertEqual(resp.selected_option_ids, [self.opt1_a.id])
        self.assertTrue(resp.is_marked_for_review)

    def test_exam_submission_scoring_and_negative_marking(self):
        """
        Submitting exam calculates:
        - Q1 answered correctly (+1.0)
        - Q2 answered incorrectly (-0.25)
        - Net score = 1.0 - 0.25 = 0.75 / 2.0 (37.5%, Failed since passing is 50%)
        """
        self.client.force_login(self.student)
        attempt, _ = ExamEvaluationService.start_or_resume_attempt(self.student, self.exam)

        # Q1: Correct
        ExamEvaluationService.save_candidate_response(attempt, self.q1.id, selected_option_ids=[self.opt1_a.id])
        # Q2: Incorrect
        ExamEvaluationService.save_candidate_response(attempt, self.q2.id, selected_option_ids=[self.opt2_b.id])

        # Submit
        finalized = ExamEvaluationService.finalize_submission(attempt)
        self.assertEqual(finalized.status, ExamAttempt.Status.SUBMITTED)
        self.assertEqual(finalized.correct_count, 1)
        self.assertEqual(finalized.incorrect_count, 1)
        self.assertEqual(float(finalized.score), 0.75)
        self.assertEqual(float(finalized.percentage), 37.5)
        self.assertFalse(finalized.passed)

        # Verify StudentSkillMastery updated
        mastery = StudentSkillMastery.objects.get(user=self.student, subject=self.subject)
        self.assertEqual(mastery.attempted_count, 2)
        self.assertEqual(mastery.correct_count, 1)
        self.assertEqual(float(mastery.accuracy_percentage), 50.0)

    # --------------------------------------------------------------------------
    # 3. CODE EXECUTION SANDBOX TESTS
    # --------------------------------------------------------------------------

    def test_python_code_execution_in_sandbox(self):
        """Python executes inside the secure sandbox returning stdout and ACCEPTED."""
        code = "print(25 + 75)"
        res = SecureExecutionSandbox.execute_code("python", code, input_data="", time_limit=3.0)
        self.assertEqual(res["status"], "ACCEPTED")
        self.assertEqual(res["output"], "100")
        self.assertGreater(res["runtime_ms"], 0.0)

    def test_sandbox_security_blocks_malicious_tokens(self):
        """Sandbox rejects prohibited system calls e.g. os.system, subprocess."""
        is_safe, err = sanitize_and_validate_code("python", "import os\nos.system('dir')")
        self.assertFalse(is_safe)
        self.assertIn("Prohibited token", err)

        res = SecureExecutionSandbox.execute_code("python", "import subprocess\nsubprocess.run(['ls'])")
        self.assertEqual(res["status"], "RUNTIME_ERROR")
        self.assertIn("Security Violation", res["error"])

    def test_coding_submission_evaluates_all_test_cases(self):
        """Coding solution evaluated against sample and hidden test cases."""
        solution = "import sys\nparts = sys.stdin.read().split()\nprint(int(parts[0]) + int(parts[1]))\n"
        res = evaluate_submission_against_problem(self.prob, solution, "python", is_submit=True)
        self.assertEqual(res["status"], "ACCEPTED")
        self.assertEqual(res["passed_count"], 2)
        self.assertEqual(res["total_count"], 2)

    # --------------------------------------------------------------------------
    # 4. ADMIN ASSESSMENT SUITE & PERMISSION TESTS
    # --------------------------------------------------------------------------

    def test_student_blocked_from_admin_assessment_hub(self):
        """Students are blocked with 403 / redirect from Admin Assessment Hub."""
        self.client.force_login(self.student)
        response = self.client.get(reverse("admin_assessment_hub"))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_access_admin_assessment_hub(self):
        """Platform Owner accesses Admin Assessment Hub with full controls."""
        self.client.force_login(self.owner)
        response = self.client.get(reverse("admin_assessment_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assessment & Examination Control Center")

    # --------------------------------------------------------------------------
    # 5. PER-EXAM ISOLATION, PRO-LEVEL SEED DATA & SECURITY TESTS
    # --------------------------------------------------------------------------

    def test_seed_exam_questions_isolation_and_zero_duplicates(self):
        """Each examination possesses exactly 14 unique, topic-specific MCQs with 0 duplicates."""
        from django.core.management import call_command
        call_command("seed_exam_questions")

        expected_exams = [
            "DBMS & SQL Query Master Live Test",
            "C Programming & Pointer Architecture Assessment",
            "CUET-PG (SCQP09) Computer Science Diagnostic Exam",
            "OJEE MCA Entrance Grand Practice Test",
            "NIMCET MCA Entrance All-India Mock Test 2024",
        ]

        exam_title_maps = {}
        exam_text_maps = {}

        for exam_title in expected_exams:
            exam = Examination.objects.get(title=exam_title)
            # Must have exactly 14 approved questions linked via exam FK
            qs = exam.questions.filter(status=Question.Status.APPROVED)
            self.assertEqual(qs.count(), 14, f"{exam_title} must have exactly 14 approved questions")

            titles = set(qs.values_list("title", flat=True))
            texts = set(qs.values_list("question_text", flat=True))
            self.assertEqual(len(titles), 14, f"All 14 titles in {exam_title} must be unique")
            self.assertEqual(len(texts), 14, f"All 14 question texts in {exam_title} must be unique")

            exam_title_maps[exam_title] = titles
            exam_text_maps[exam_title] = texts

            # Verify options and explanations for all 14 questions
            correct_keys = []
            for q in qs:
                self.assertEqual(q.options.count(), 4, f"Question '{q.title}' must have 4 options")
                correct_opts = q.options.filter(is_correct=True)
                self.assertEqual(correct_opts.count(), 1, f"Question '{q.title}' must have exactly 1 correct answer")
                correct_keys.append(correct_opts.first().option_key)
                self.assertTrue(hasattr(q, "explanation_detail"), f"Question '{q.title}' must have an explanation")

            # Check balanced A, B, C, D distribution (no option key should have 0 or all counts)
            for key in ["A", "B", "C", "D"]:
                self.assertIn(key, correct_keys, f"Exam {exam_title} must feature option {key} among correct answers")

        # Verify pairwise ZERO overlap between any two exams
        titles_list = list(exam_title_maps.keys())
        for i in range(len(titles_list)):
            for j in range(i + 1, len(titles_list)):
                e1 = titles_list[i]
                e2 = titles_list[j]
                title_overlap = exam_title_maps[e1].intersection(exam_title_maps[e2])
                text_overlap = exam_text_maps[e1].intersection(exam_text_maps[e2])
                self.assertEqual(len(title_overlap), 0, f"Exams '{e1}' and '{e2}' share question titles: {title_overlap}")
                self.assertEqual(len(text_overlap), 0, f"Exams '{e1}' and '{e2}' share question texts: {text_overlap}")

    def test_exam_negative_marking_enforced_by_exam_settings(self):
        """Scoring strictly adheres to exam-specific negative marking settings (DBMS: -0.25, C: 0.00)."""
        from django.core.management import call_command
        call_command("seed_exam_questions")

        # 1. Test DBMS Exam (-0.25 rate)
        dbms_exam = Examination.objects.get(title="DBMS & SQL Query Master Live Test")
        self.assertEqual(float(dbms_exam.negative_marking_rate), 0.25)
        attempt_dbms, _ = ExamEvaluationService.start_or_resume_attempt(self.student, dbms_exam)

        q_dbms = dbms_exam.questions.first()
        incorrect_opt_dbms = q_dbms.options.filter(is_correct=False).first()

        resp_dbms_obj = ExamResponse.objects.get(attempt=attempt_dbms, question=q_dbms)
        resp_dbms_obj.selected_option_ids = [incorrect_opt_dbms.id]
        resp_dbms_obj.save()

        finalized_dbms = ExamEvaluationService.finalize_submission(attempt_dbms)
        resp_dbms = finalized_dbms.responses.get(question=q_dbms)
        self.assertFalse(resp_dbms.is_correct)
        self.assertEqual(float(resp_dbms.marks_awarded), -0.25)

        # 2. Test C Programming Exam (0.00 rate)
        c_exam = Examination.objects.get(title="C Programming & Pointer Architecture Assessment")
        self.assertEqual(float(c_exam.negative_marking_rate), 0.00)
        attempt_c, _ = ExamEvaluationService.start_or_resume_attempt(self.student, c_exam)

        q_c = c_exam.questions.first()
        incorrect_opt_c = q_c.options.filter(is_correct=False).first()

        resp_c_obj = ExamResponse.objects.get(attempt=attempt_c, question=q_c)
        resp_c_obj.selected_option_ids = [incorrect_opt_c.id]
        resp_c_obj.save()

        finalized_c = ExamEvaluationService.finalize_submission(attempt_c)
        resp_c = finalized_c.responses.get(question=q_c)
        self.assertFalse(resp_c.is_correct)
        self.assertEqual(float(resp_c.marks_awarded), 0.00)

    def test_live_exam_security_never_leaks_answers_or_explanations(self):
        """Client-side HTML on live exam page never leaks is_correct or explanation before submission."""
        from django.core.management import call_command
        call_command("seed_exam_questions")

        dbms_exam = Examination.objects.get(title="DBMS & SQL Query Master Live Test")
        attempt, _ = ExamEvaluationService.start_or_resume_attempt(self.student, dbms_exam)

        self.client.force_login(self.student)
        url = reverse("exam_live", kwargs={"attempt_id": attempt.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        # Ensure is_correct and explanations are NOT present in client HTML
        self.assertNotIn('is_correct', content)
        self.assertNotIn('explanation_detail', content)
        self.assertNotIn('why_correct', content)

    def test_navbar_owner_control_center_and_actions_layout(self):
        """Navbar renders Owner Control Center with shield and text inside single header-actions flex."""
        self.client.force_login(self.owner)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("nav-link-owner", content)
        self.assertIn("owner-shield-icon", content)
        self.assertIn("Owner Control Center", content)
        self.assertIn("cmdPaletteTriggerBtn", content)
        self.assertIn("header-actions", content)


class EntranceAssessmentRebuildTests(TestCase):
    """
    Automated verification of the Rebuilt Entrance Exam & MCQ Assessment Engine:
    1. Every exam has exactly 16 questions and 21 minutes duration.
    2. Every question has 4 options and exactly 1 correct option.
    3. No question is shared between exams. No duplicate question text.
    4. Attempt limit: 5th attempt is rejected with an error; max 4 attempts strictly enforced.
    5. Resuming an in-progress attempt does not consume a new attempt.
    6. Late submission (> deadline + 5s) auto-submits / rejects further answers.
    7. Decimal scoring: +1.00 correct, -0.25 wrong, 0.00 unanswered. Total 16.00 marks.
    8. Live exam page HTML contains no is_correct or explanations.
    9. User attempt isolation: User B cannot view User A's live attempt or submit answers to it.
    10. seed_entrance_questions idempotency: running it twice leaves counts unchanged.
    """

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        # Seed the entrance exam architecture
        call_command("seed_entrance_questions", replace=True)

        cls.user_a = User.objects.create_user(
            username="candidate_alpha",
            email="candidate_alpha@hirenexa.internal",
            password="AlphaPassword123!",
            role=User.Role.CANDIDATE,
            is_active=True,
        )
        cls.user_b = User.objects.create_user(
            username="candidate_beta",
            email="candidate_beta@hirenexa.internal",
            password="BetaPassword123!",
            role=User.Role.CANDIDATE,
            is_active=True,
        )

    def setUp(self):
        self.client_a = Client()
        self.client_a.force_login(self.user_a)

        self.client_b = Client()
        self.client_b.force_login(self.user_b)

    def test_01_all_exams_have_16_questions_and_21_minutes(self):
        """Rule 1: Every exam in the database has exactly 16 questions and 21 minutes duration."""
        exams = Examination.objects.filter(is_published=True, is_active=True)
        self.assertGreater(exams.count(), 0, "Database must have active examinations.")
        for exam in exams:
            self.assertEqual(
                exam.duration_minutes, 21,
                f"Exam '{exam.title}' ({exam.slug}) must have duration_minutes=21, got {exam.duration_minutes}"
            )
            q_count = exam.questions.count()
            self.assertEqual(
                q_count, 16,
                f"Exam '{exam.title}' ({exam.slug}) must have exactly 16 questions, got {q_count}"
            )
            self.assertEqual(
                exam.total_marks, Decimal("16.00"),
                f"Exam '{exam.title}' must have total_marks=16.00"
            )
            self.assertEqual(
                exam.max_attempts, 5,
                f"Exam '{exam.title}' must have max_attempts=5"
            )
            self.assertEqual(
                exam.negative_marking, Decimal("0.25"),
                f"Exam '{exam.title}' must have negative_marking=0.25"
            )

    def test_02_every_question_has_4_options_and_1_correct(self):
        """Rule 2: Every question has 4 options and exactly 1 correct option."""
        questions = Question.objects.filter(status=Question.Status.APPROVED)
        self.assertGreater(questions.count(), 0)
        for q in questions:
            opts = list(q.options.all())
            self.assertEqual(
                len(opts), 4,
                f"Question ID {q.id} '{q.title}' must have exactly 4 options, found {len(opts)}"
            )
            correct_opts = [o for o in opts if o.is_correct]
            self.assertEqual(
                len(correct_opts), 1,
                f"Question ID {q.id} '{q.title}' must have exactly 1 correct option, found {len(correct_opts)}"
            )

    def test_03_no_question_shared_between_exams_and_no_duplicates(self):
        """Rule 3: No question is shared between exams. No duplicate question text."""
        unlinked_qs = Question.objects.filter(exam__isnull=True)
        self.assertEqual(unlinked_qs.count(), 0, "All entrance questions must belong to an exam.")

        exams = list(Examination.objects.filter(is_published=True, is_active=True).prefetch_related("questions"))
        seen_qids = set()
        for exam in exams:
            exam_qids = set(exam.questions.values_list("id", flat=True))
            overlap = seen_qids.intersection(exam_qids)
            self.assertEqual(
                len(overlap), 0,
                f"Exam '{exam.title}' shares questions {overlap} with other examinations!"
            )
            seen_qids.update(exam_qids)

        for exam in exams:
            texts = list(exam.questions.values_list("question_text", flat=True))
            normalized = [t.strip().lower() for t in texts]
            self.assertEqual(
                len(normalized), len(set(normalized)),
                f"Exam '{exam.title}' contains duplicate question texts!"
            )

    def test_04_attempt_limit_5th_attempt_rejected(self):
        """Rule 4: Attempt limit: (max_attempts + 1)th attempt is rejected with an error; strictly enforced."""
        exam = Examination.objects.filter(is_final_combined=False, is_published=True, is_active=True).first()
        self.assertIsNotNone(exam)

        ExamAttempt.objects.filter(user=self.user_a, examination=exam).delete()
        limit = exam.max_attempts or 5

        # Create attempts 1 through limit
        for i in range(1, limit + 1):
            att, created = ExamEvaluationService.start_or_resume_attempt(self.user_a, exam)
            self.assertTrue(created)
            self.assertEqual(att.attempt_number, i)
            ExamEvaluationService.finalize_submission(att)

        # (limit + 1)th attempt via service must raise PermissionError
        with self.assertRaises(PermissionError):
            ExamEvaluationService.start_or_resume_attempt(self.user_a, exam)

        # (limit + 1)th attempt via POST request to exam_start must be blocked
        response = self.client_a.post(reverse("exam_start", kwargs={"exam_slug": exam.slug}), follow=True)
        self.assertEqual(response.status_code, 200)
        messages_list = list(response.context["messages"])
        self.assertTrue(any("maximum" in str(m).lower() for m in messages_list))

        # Verify DB still has exactly limit attempts
        total_attempts = ExamAttempt.objects.filter(user=self.user_a, examination=exam).count()
        self.assertEqual(total_attempts, limit)

    def test_05_resuming_in_progress_attempt_does_not_consume_new_attempt(self):
        """Rule 5: Resuming an in-progress attempt returns existing attempt and does not consume a new attempt."""
        exam = Examination.objects.filter(is_final_combined=False, is_published=True, is_active=True).first()
        ExamAttempt.objects.filter(user=self.user_b, examination=exam).delete()

        # Start attempt 1
        att1, created1 = ExamEvaluationService.start_or_resume_attempt(self.user_b, exam)
        self.assertTrue(created1)
        self.assertEqual(att1.attempt_number, 1)
        self.assertEqual(att1.status, ExamAttempt.Status.IN_PROGRESS)

        # Call start_or_resume again
        att2, created2 = ExamEvaluationService.start_or_resume_attempt(self.user_b, exam)
        self.assertFalse(created2)
        self.assertEqual(att1.id, att2.id)
        self.assertEqual(att2.attempt_number, 1)

        count = ExamAttempt.objects.filter(user=self.user_b, examination=exam).count()
        self.assertEqual(count, 1)

    def test_06_late_submission_past_deadline_plus_grace_period(self):
        """Rule 6: Late submission (> deadline + 5s) auto-submits / rejects further answers."""
        exam = Examination.objects.filter(is_final_combined=False, is_published=True, is_active=True).first()
        ExamAttempt.objects.filter(user=self.user_a, examination=exam).delete()

        att, _ = ExamEvaluationService.start_or_resume_attempt(self.user_a, exam)
        att.deadline = timezone.now() - timezone.timedelta(seconds=10)
        att.save(update_fields=["deadline"])

        q = exam.questions.first()
        opt = q.options.first()

        result = ExamEvaluationService.save_candidate_response(
            att, q.id, selected_option_ids=[opt.id]
        )
        self.assertFalse(result["success"])
        self.assertTrue(result.get("timed_out"))

        att.refresh_from_db()
        self.assertIn(att.status, [ExamAttempt.Status.EXPIRED, ExamAttempt.Status.SUBMITTED])

    def test_07_decimal_scoring_and_total_marks(self):
        """Rule 7: Decimal scoring: +1.00 correct, -0.25 wrong, 0.00 unanswered. Total 16.00 marks."""
        exam = Examination.objects.filter(is_final_combined=False, is_published=True, is_active=True).first()
        ExamAttempt.objects.filter(user=self.user_a, examination=exam).delete()

        att, _ = ExamEvaluationService.start_or_resume_attempt(self.user_a, exam)
        questions = list(exam.questions.all().order_by("order", "id"))
        self.assertEqual(len(questions), 16)

        # Answer 10 correctly (+10.00), 4 incorrectly (-1.00), 2 skipped (0.00)
        for i in range(10):
            q = questions[i]
            correct_opt = q.options.filter(is_correct=True).first()
            ExamEvaluationService.save_candidate_response(att, q.id, selected_option_ids=[correct_opt.id])

        for i in range(10, 14):
            q = questions[i]
            wrong_opt = q.options.filter(is_correct=False).first()
            ExamEvaluationService.save_candidate_response(att, q.id, selected_option_ids=[wrong_opt.id])

        finalized = ExamEvaluationService.finalize_submission(att)
        self.assertEqual(finalized.correct_count, 10)
        self.assertEqual(finalized.incorrect_count, 4)
        self.assertEqual(finalized.skipped_count, 2)

        # Expected score = 10 * 1.00 - 4 * 0.25 = 9.00
        self.assertEqual(finalized.score, Decimal("9.00"))
        self.assertEqual(finalized.total_possible_marks, Decimal("16.00"))
        # Expected percentage = (9.00 / 16.00) * 100 = 56.25%
        self.assertEqual(finalized.percentage, Decimal("56.25"))

    def test_08_live_exam_page_never_leaks_is_correct_or_explanations(self):
        """Rule 8: Live exam page HTML contains no is_correct or explanations."""
        exam = Examination.objects.filter(is_final_combined=False, is_published=True, is_active=True).first()
        ExamAttempt.objects.filter(user=self.user_a, examination=exam).delete()
        att, _ = ExamEvaluationService.start_or_resume_attempt(self.user_a, exam)

        response = self.client_a.get(reverse("exam_live", kwargs={"attempt_id": att.id}))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")
        self.assertNotIn("is_correct", html)
        self.assertNotIn("explanation", html)
        self.assertNotIn("why_correct", html)
        self.assertNotIn("step_by_step_logic", html)

    def test_09_user_attempt_isolation(self):
        """Rule 9: User attempt isolation: User B cannot view User A's live attempt or submit answers to it."""
        exam = Examination.objects.filter(is_final_combined=False, is_published=True, is_active=True).first()
        ExamAttempt.objects.filter(user=self.user_a, examination=exam).delete()
        att_a, _ = ExamEvaluationService.start_or_resume_attempt(self.user_a, exam)

        # User B attempts to access User A's live exam page
        response = self.client_b.get(reverse("exam_live", kwargs={"attempt_id": att_a.id}))
        self.assertEqual(response.status_code, 404)

        # User B attempts to save an answer to User A's attempt
        q = exam.questions.first()
        save_url = reverse("api_exam_save_answer", kwargs={"attempt_id": att_a.id})
        payload = {"question_id": q.id, "selected_option_ids": [q.options.first().id]}
        post_resp = self.client_b.post(save_url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(post_resp.status_code, 404)

        # User B attempts to submit User A's attempt
        submit_url = reverse("api_exam_submit", kwargs={"attempt_id": att_a.id})
        submit_resp = self.client_b.post(submit_url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(submit_resp.status_code, 404)

    def test_10_seed_entrance_questions_idempotency(self):
        """Rule 10: seed_entrance_questions idempotency: running it twice leaves counts unchanged."""
        from django.core.management import call_command
        exam_count_before = Examination.objects.count()
        question_count_before = Question.objects.count()
        option_count_before = QuestionOption.objects.count()

        call_command("seed_entrance_questions")

        exam_count_after = Examination.objects.count()
        question_count_after = Question.objects.count()
        option_count_after = QuestionOption.objects.count()

        self.assertEqual(exam_count_before, exam_count_after, "Exam count must remain unchanged after re-running seed.")
        self.assertEqual(question_count_before, question_count_after, "Question count must remain unchanged.")
        self.assertEqual(option_count_before, option_count_after, "Option count must remain unchanged.")


class EntrancePlatformUpgradeTests(TestCase):
    """
    Automated regression tests verifying the advanced entrance platform requirements:
    - Subject & Topic Question Bank Isolation (0 cross-contamination).
    - Unseen Question Rotation across multiple attempts using UserQuestionHistory.
    - 4 Question Statuses (Answered, Unanswered, Marked, Answered & Marked).
    - Prerequisite Topic Completion and Final Combined Exam Lock Gate.
    - Practice Wrong Questions drill session generation.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="candidate_john",
            email="candidate_john@hirenexa.internal",
            password="StrongPassword123!",
            role=User.Role.CANDIDATE,
            is_active=True,
            is_email_verified=True,
        )
        self.client.force_login(self.user)

        # Subject: Computer Organization & Architecture
        self.subject = Subject.objects.create(
            name="Computer Organization and Architecture",
            slug="computer-organization-and-architecture",
            category=Subject.Category.CORE_CS,
            order=10
        )
        self.topic_num_rep = Topic.objects.create(
            subject=self.subject,
            name="Number Representation",
            slug="number-representation",
            order=1
        )
        self.topic_io = Topic.objects.create(
            subject=self.subject,
            name="I/O and Interrupts",
            slug="io-and-interrupts",
            order=2
        )

    def test_topic_question_strict_isolation(self):
        """Verifies that questions generated for Number Representation never leak into I/O and Interrupts."""
        from assessments.question_engine import generate_questions_for_topic
        num_qs = generate_questions_for_topic("computer-organization-and-architecture", "Computer Organization and Architecture", "Number Representation", count=16)
        io_qs = generate_questions_for_topic("computer-organization-and-architecture", "Computer Organization and Architecture", "I/O and Interrupts", count=16)

        self.assertEqual(len(num_qs), 16)
        self.assertEqual(len(io_qs), 16)

        # Verify Number Representation questions only contain number representation concepts
        for q in num_qs:
            q_full = (q["text"] + " " + q["explanation"] + " " + " ".join(o["text"] for o in q["options"])).lower()
            self.assertTrue(
                any(term in q_full for term in ["2's complement", "ieee-754", "overflow", "exponent", "signed", "binary"]),
                f"Question {q['order']} in Number Representation lacks expected domain terms: {q['text']}"
            )
            # Must NEVER contain I/O and Interrupts terms
            self.assertNotIn("interrupt service routine", q_full)
            self.assertNotIn("cycle stealing", q_full)
            self.assertNotIn("vectored interrupt", q_full)

        # Verify I/O and Interrupts questions only contain I/O concepts
        for q in io_qs:
            q_full = (q["text"] + " " + q["explanation"] + " " + " ".join(o["text"] for o in q["options"])).lower()
            self.assertTrue(
                any(term in q_full for term in ["interrupt", "dma", "isr", "latency", "memory-mapped"]),
                f"Question {q['order']} in I/O and Interrupts lacks expected domain terms: {q['text']}"
            )
            # Must NEVER contain IEEE-754 or floating point terms
            self.assertNotIn("ieee-754", q_full)
            self.assertNotIn("biased exponent", q_full)

    def test_unseen_question_rotation_across_attempts(self):
        """Rule: Attempt 1 and Attempt 2 draw distinct, unseen question sets using UserQuestionHistory."""
        exam = Examination.objects.create(
            title="Number Representation Topic Test",
            slug="num-rep-rotation-test",
            kind=Examination.Kind.TOPIC_TEST,
            subject=self.subject,
            topic=self.topic_num_rep,
            duration_minutes=21,
            max_attempts=4,
            total_marks=Decimal("16.00"),
            negative_marking=Decimal("0.25"),
            is_published=True,
            is_active=True,
        )

        # Seed 32 approved questions into this exam (enough for 2 distinct attempts)
        for i in range(1, 33):
            diff = Question.Level.EASY if i <= 8 else (Question.Level.MEDIUM if i <= 24 else Question.Level.HARD)
            q = Question.objects.create(
                exam=exam,
                subject=self.subject,
                topic=self.topic_num_rep,
                order=i,
                title=f"Unique Number Representation Problem #{i}",
                question_text=f"What is the binary representation of #{i}?",
                difficulty=diff,
                marks=Decimal("1.00"),
                negative_marks=Decimal("0.25"),
                status=Question.Status.APPROVED,
            )
            QuestionOption.objects.create(question=q, option_key="A", option_text=f"Answer {i}", is_correct=True)
            QuestionOption.objects.create(question=q, option_key="B", option_text=f"Distractor 1", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="C", option_text=f"Distractor 2", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="D", option_text=f"Distractor 3", is_correct=False)

        # Attempt 1
        att1, _ = ExamEvaluationService.start_or_resume_attempt(self.user, exam)
        self.assertEqual(len(att1.ordered_question_ids), 16)
        qids_att1 = set(att1.ordered_question_ids)

        # Submit Attempt 1
        ExamEvaluationService.finalize_submission(att1)

        # Attempt 2
        att2, _ = ExamEvaluationService.start_or_resume_attempt(self.user, exam)
        self.assertEqual(len(att2.ordered_question_ids), 16)
        qids_att2 = set(att2.ordered_question_ids)

        # Overlap must be ZERO because pool had 32 questions and 16 were seen in attempt 1
        overlap = qids_att1.intersection(qids_att2)
        self.assertEqual(len(overlap), 0, f"Attempt 2 contained repeated questions: {overlap}")

        # Verify UserQuestionHistory recorded both sets
        history_cnt = UserQuestionHistory.objects.filter(user=self.user, examination=exam).count()
        self.assertEqual(history_cnt, 32)

    def test_four_question_statuses_and_review(self):
        """Verifies Answered, Unanswered, Marked for Review, and Answered & Marked statuses."""
        exam = Examination.objects.create(
            title="Status Verification Test",
            slug="status-verif-test",
            kind=Examination.Kind.TOPIC_TEST,
            subject=self.subject,
            topic=self.topic_num_rep,
            duration_minutes=21,
            max_attempts=4,
            total_marks=Decimal("16.00"),
            negative_marking=Decimal("0.25"),
            is_published=True,
            is_active=True,
            shuffle_questions=False,
        )
        for i in range(1, 17):
            q = Question.objects.create(
                exam=exam,
                subject=self.subject,
                topic=self.topic_num_rep,
                order=i,
                title=f"Status Test Q{i}",
                question_text=f"Prompt for Q{i}",
                difficulty=Question.Level.MEDIUM,
                marks=Decimal("1.00"),
                negative_marks=Decimal("0.25"),
                status=Question.Status.APPROVED,
            )
            QuestionOption.objects.create(question=q, option_key="A", option_text="Opt A", is_correct=True)
            QuestionOption.objects.create(question=q, option_key="B", option_text="Opt B", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="C", option_text="Opt C", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="D", option_text="Opt D", is_correct=False)

        att, _ = ExamEvaluationService.start_or_resume_attempt(self.user, exam)
        q_objs = list(exam.questions.all().order_by("order"))

        # Q1: Answered only (is_marked_for_review=False)
        opt_a = q_objs[0].options.first()
        res1 = ExamEvaluationService.save_candidate_response(att, q_objs[0].id, selected_option_ids=[opt_a.id], is_marked_for_review=False)
        self.assertTrue(res1["has_answer"])
        self.assertFalse(res1["is_marked_for_review"])

        # Q2: Marked for review only (no option selected)
        res2 = ExamEvaluationService.save_candidate_response(att, q_objs[1].id, selected_option_ids=[], is_marked_for_review=True)
        self.assertFalse(res2["has_answer"])
        self.assertTrue(res2["is_marked_for_review"])

        # Q3: Answered AND Marked for review
        res3 = ExamEvaluationService.save_candidate_response(att, q_objs[2].id, selected_option_ids=[q_objs[2].options.first().id], is_marked_for_review=True)
        self.assertTrue(res3["has_answer"])
        self.assertTrue(res3["is_marked_for_review"])

        # Q4..Q16: Unanswered / Skipped

        # Verify live page palette statuses
        resp = self.client.get(reverse("exam_live", kwargs={"attempt_id": att.id}))
        self.assertEqual(resp.status_code, 200)
        palette = resp.context["palette"]

        p_q0 = next(p for p in palette if p["question_id"] == q_objs[0].id)
        p_q1 = next(p for p in palette if p["question_id"] == q_objs[1].id)
        p_q2 = next(p for p in palette if p["question_id"] == q_objs[2].id)
        p_q3 = next(p for p in palette if p["question_id"] == q_objs[3].id)

        self.assertEqual(p_q0["status_class"], "answered")
        self.assertEqual(p_q1["status_class"], "marked-review")
        self.assertEqual(p_q2["status_class"], "answered-review")
        self.assertEqual(p_q3["status_class"], "unanswered")

    def test_final_combined_exam_lock_gate(self):
        """Verifies Final Combined Exam is locked until all required topics are completed."""
        combined_exam = Examination.objects.create(
            title="COA Grand Final Examination",
            slug="coa-grand-final-exam",
            kind=Examination.Kind.MOCK_TEST,
            subject=self.subject,
            is_final_combined=True,
            required_topics_count=2,  # requires both topics to be completed
            duration_minutes=21,
            max_attempts=4,
            total_marks=Decimal("16.00"),
            negative_marking=Decimal("0.25"),
            is_published=True,
            is_active=True,
        )

        # Candidate attempts to start without completing topics -> blocked by lock
        with self.assertRaises(PermissionError):
            ExamEvaluationService.start_or_resume_attempt(self.user, combined_exam)

        # Complete Topic 1 (Number Representation)
        TopicCompletion.objects.create(user=self.user, topic=self.topic_num_rep, is_completed=True, best_score=Decimal("14.00"))

        # Still blocked because 1 < 2
        with self.assertRaises(PermissionError):
            ExamEvaluationService.start_or_resume_attempt(self.user, combined_exam)

        # Complete Topic 2 (I/O and Interrupts)
        TopicCompletion.objects.create(user=self.user, topic=self.topic_io, is_completed=True, best_score=Decimal("12.00"))

        # Seed 16 questions for combined exam
        for i in range(1, 17):
            q = Question.objects.create(
                exam=combined_exam,
                subject=self.subject,
                order=i,
                title=f"Combined Q{i}",
                question_text=f"Combined Prompt {i}",
                difficulty=Question.Level.MEDIUM,
                marks=Decimal("1.00"),
                negative_marks=Decimal("0.25"),
                status=Question.Status.APPROVED,
            )
            QuestionOption.objects.create(question=q, option_key="A", option_text="Opt A", is_correct=True)
            QuestionOption.objects.create(question=q, option_key="B", option_text="Opt B", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="C", option_text="Opt C", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="D", option_text="Opt D", is_correct=False)

        # Now unlocked! Start succeeds without PermissionError
        attempt, created = ExamEvaluationService.start_or_resume_attempt(self.user, combined_exam)
        self.assertTrue(created)
        self.assertEqual(attempt.status, ExamAttempt.Status.IN_PROGRESS)

    def test_practice_wrong_questions_drill(self):
        """Verifies practice session contains only incorrect and skipped questions without mutating original score."""
        exam = Examination.objects.create(
            title="Drill Test",
            slug="drill-test-exam",
            kind=Examination.Kind.TOPIC_TEST,
            subject=self.subject,
            topic=self.topic_num_rep,
            duration_minutes=21,
            max_attempts=4,
            total_marks=Decimal("16.00"),
            negative_marking=Decimal("0.25"),
            is_published=True,
            is_active=True,
        )
        for i in range(1, 17):
            q = Question.objects.create(
                exam=exam,
                subject=self.subject,
                topic=self.topic_num_rep,
                order=i,
                title=f"Drill Q{i}",
                question_text=f"Question text {i}",
                difficulty=Question.Level.EASY if i <= 4 else Question.Level.MEDIUM,
                marks=Decimal("1.00"),
                negative_marks=Decimal("0.25"),
                status=Question.Status.APPROVED,
            )
            QuestionOption.objects.create(question=q, option_key="A", option_text="Correct", is_correct=True)
            QuestionOption.objects.create(question=q, option_key="B", option_text="Wrong 1", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="C", option_text="Wrong 2", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="D", option_text="Wrong 3", is_correct=False)

        att, _ = ExamEvaluationService.start_or_resume_attempt(self.user, exam)
        questions = list(exam.questions.all().order_by("order"))

        # 10 Correct, 4 Incorrect, 2 Skipped
        for i in range(10):
            correct_opt = questions[i].options.filter(is_correct=True).first()
            ExamEvaluationService.save_candidate_response(att, questions[i].id, selected_option_ids=[correct_opt.id])

        for i in range(10, 14):
            wrong_opt = questions[i].options.filter(is_correct=False).first()
            ExamEvaluationService.save_candidate_response(att, questions[i].id, selected_option_ids=[wrong_opt.id])

        finalized = ExamEvaluationService.finalize_submission(att)
        self.assertEqual(finalized.correct_count, 10)
        self.assertEqual(finalized.incorrect_count, 4)
        self.assertEqual(finalized.skipped_count, 2)
        original_score = finalized.score

        # Access practice wrong questions view
        url = reverse("practice_wrong_questions", kwargs={"attempt_id": finalized.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Context must contain exactly 6 questions (4 incorrect + 2 skipped)
        self.assertEqual(response.context["wrong_count"], 6)

        # Original score must remain untouched
        refreshed_attempt = ExamAttempt.objects.get(id=finalized.id)
        self.assertEqual(refreshed_attempt.score, original_score)

    def test_exam_live_view_rehydrates_saved_state_and_options(self):
        """Verifies that exam_live_view passes saved_state_json in context with saved selections."""
        exam = Examination.objects.create(
            title="Rehydration Test Exam",
            slug="rehydration-test-exam",
            kind=Examination.Kind.TOPIC_TEST,
            subject=self.subject,
            duration_minutes=21,
            max_attempts=4,
            is_published=True,
            is_active=True,
        )
        q = Question.objects.create(
            exam=exam,
            subject=self.subject,
            order=1,
            title="Rehydration Q1",
            question_text="Sample text",
            difficulty=Question.Level.BEGINNER,
            status=Question.Status.APPROVED,
        )
        opt_a = QuestionOption.objects.create(question=q, option_key="A", option_text="Opt A", is_correct=True)
        opt_b = QuestionOption.objects.create(question=q, option_key="B", option_text="Opt B", is_correct=False)
        opt_c = QuestionOption.objects.create(question=q, option_key="C", option_text="Opt C", is_correct=False)
        opt_d = QuestionOption.objects.create(question=q, option_key="D", option_text="Opt D", is_correct=False)

        att, _ = ExamEvaluationService.start_or_resume_attempt(self.user, exam)
        # Save response for Q1 with option B selected
        ExamEvaluationService.save_candidate_response(att, q.id, selected_option_ids=[opt_b.id], is_marked_for_review=True)

        url = reverse("exam_live", kwargs={"attempt_id": att.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # saved_state_json must be present in context
        self.assertIn("saved_state_json", response.context)
        state_data = json.loads(response.context["saved_state_json"])
        self.assertIn("1", state_data)
        self.assertTrue(state_data["1"]["answered"])
        self.assertTrue(state_data["1"]["review"])
        self.assertEqual(state_data["1"]["selectedOption"], opt_b.id)

        # q.user_selected_option_ids must contain opt_b.id
        questions_in_ctx = response.context["questions"]
        self.assertEqual(len(questions_in_ctx), 1)
        self.assertEqual(questions_in_ctx[0].user_selected_option_ids, [opt_b.id])

    def test_exam_result_view_has_max_attempts_and_attempts_left(self):
        """Verifies that exam_result_view correctly computes and supplies max_attempts and attempts_left."""
        exam = Examination.objects.create(
            title="Result Context Test",
            slug="result-context-test",
            kind=Examination.Kind.TOPIC_TEST,
            subject=self.subject,
            duration_minutes=21,
            max_attempts=4,
            is_published=True,
            is_active=True,
        )
        q = Question.objects.create(
            exam=exam,
            subject=self.subject,
            order=1,
            title="Result Q1",
            question_text="Prompt 1",
            status=Question.Status.APPROVED,
        )
        opt_a = QuestionOption.objects.create(question=q, option_key="A", option_text="Opt A", is_correct=True)
        opt_b = QuestionOption.objects.create(question=q, option_key="B", option_text="Opt B", is_correct=False)
        opt_c = QuestionOption.objects.create(question=q, option_key="C", option_text="Opt C", is_correct=False)
        opt_d = QuestionOption.objects.create(question=q, option_key="D", option_text="Opt D", is_correct=False)

        att, _ = ExamEvaluationService.start_or_resume_attempt(self.user, exam)
        finalized = ExamEvaluationService.finalize_submission(att)

        url = reverse("exam_result", kwargs={"attempt_id": finalized.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Context must contain max_attempts and attempts_left
        self.assertEqual(response.context["max_attempts"], 4)
        self.assertEqual(response.context["attempts_left"], 3)
        self.assertContains(response, "Attempt 1 of 4")
        self.assertContains(response, "Retake Test (3 of 4 Left)")


class UltraProEntranceEcosystemTests(TestCase):
    """
    Exhaustive Test Suite for Ultra Pro Entrance Examination Ecosystem:
    1. Exact Benchmark Scoring Formulas: 16 Qs, 12 correct, 3 incorrect, 1 skipped -> Final 11.25/16, Score 70.31%, Accuracy 80%, Completion 93.75%.
    2. Mandatory 16 Qs, 21 Mins, 5 Attempts, 4/7/5 Difficulty Balance.
    3. Anti-Repetition Engine, SHA-256 Fingerprints & Question Exposure History.
    4. Question Bank Shortage Error (< 16 questions).
    5. Independent Entrance Preparation Tracks (MCA & MBA).
    6. Topic Learning Notes Structure & CBT 4 Question States.
    7. Multi-Attempt Score Progression & Personal Target Gap Analysis.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="entrance_candidate",
            email="candidate@hirenexa.internal",
            password="CandidatePass123!",
            role=User.Role.CANDIDATE,
            is_active=True,
            is_email_verified=True,
        )
        self.client.force_login(self.user)

        # Entrance Track
        self.track = EntranceTrack.objects.create(
            name="MCA Entrance Preparation",
            code="MCA",
            slug="mca-entrance",
            target_exams=["NIMCET", "OJEE MCA"],
            order=1,
            is_active=True,
        )

        # Subject & Topic
        self.subject = Subject.objects.create(
            entrance_track=self.track,
            name="Mathematics (MCA)",
            slug="mathematics-mca",
            category=Subject.Category.MATHEMATICS,
            order=1,
            is_active=True,
        )
        self.topic = Topic.objects.create(
            subject=self.subject,
            name="Matrices and Determinants",
            slug="matrices-and-determinants",
            order=1,
        )

        # Topic Test Examination
        self.exam = Examination.objects.create(
            title="Matrices and Determinants Test",
            slug="matrices-and-determinants-test",
            kind=Examination.Kind.TOPIC_TEST,
            entrance_track=self.track,
            subject=self.subject,
            topic=self.topic,
            duration_minutes=21,
            total_marks=Decimal("16.00"),
            max_attempts=5,
            negative_marking=Decimal("0.25"),
            is_published=True,
            is_active=True,
        )

    def _seed_16_verified_questions(self, count=16):
        """Helper to create exactly 16 verified, non-duplicate questions."""
        questions = []
        for i in range(1, count + 1):
            diff = Question.Level.BEGINNER if i <= 4 else (Question.Level.INTERMEDIATE if i <= 11 else Question.Level.ADVANCED)
            q = Question.objects.create(
                subject=self.subject,
                topic=self.topic,
                exam=self.exam,
                order=i,
                title=f"[Matrices and Determinants] Q{i}: Determinant Invariant #{i}",
                question_text=f"Find the determinant value under condition #{i} with scale {i * 2}.",
                question_type=Question.Type.MCQ,
                difficulty=diff,
                marks=Decimal("1.00"),
                negative_marks=Decimal("0.25"),
                is_verified=True,
                status=Question.Status.APPROVED,
            )
            q.fingerprint = q.compute_fingerprint()
            q.save()
            QuestionOption.objects.create(question=q, option_key="A", option_text=f"Ans {i}", is_correct=True)
            QuestionOption.objects.create(question=q, option_key="B", option_text=f"Wrong 1-{i}", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="C", option_text=f"Wrong 2-{i}", is_correct=False)
            QuestionOption.objects.create(question=q, option_key="D", option_text=f"Wrong 3-{i}", is_correct=False)
            questions.append(q)
        return questions

    def test_mandatory_settings_and_exact_benchmark_scoring(self):
        """
        Tests the exact mandatory user benchmark:
        16 questions, 21 minutes, 5 attempts, +1 / -0.25 marking.
        12 correct, 3 incorrect, 1 skipped ->
        Positive: 12.00, Negative: 0.75, Final Score: 11.25 / 16.00.
        Score %: 70.31%, Accuracy %: 80.00%, Completion %: 93.75%.
        """
        self._seed_16_verified_questions(16)

        self.assertEqual(self.exam.duration_minutes, 21)
        self.assertEqual(self.exam.max_attempts, 5)
        self.assertEqual(self.exam.total_marks, Decimal("16.00"))
        self.assertEqual(self.exam.negative_marking, Decimal("0.25"))

        attempt, created = ExamEvaluationService.start_or_resume_attempt(self.user, self.exam)
        self.assertTrue(created)
        self.assertEqual(attempt.total_questions, 16)

        # Retrieve questions in attempt order
        attempt_q_ids = attempt.ordered_question_ids
        self.assertEqual(len(attempt_q_ids), 16)

        # 12 Correct (Questions 0 to 11)
        for i in range(12):
            qid = attempt_q_ids[i]
            corr_opt = QuestionOption.objects.filter(question_id=qid, is_correct=True).first()
            ExamEvaluationService.save_candidate_response(attempt, qid, selected_option_ids=[corr_opt.id])

        # 3 Incorrect (Questions 12 to 14)
        for i in range(12, 15):
            qid = attempt_q_ids[i]
            inc_opt = QuestionOption.objects.filter(question_id=qid, is_correct=False).first()
            ExamEvaluationService.save_candidate_response(attempt, qid, selected_option_ids=[inc_opt.id])

        # 1 Skipped (Question 15) -> No answer saved

        # Finalize submission
        finalized = ExamEvaluationService.finalize_submission(attempt)

        # Exact Score Verification
        self.assertEqual(finalized.correct_count, 12)
        self.assertEqual(finalized.incorrect_count, 3)
        self.assertEqual(finalized.skipped_count, 1)

        # Positive Marks: 12 * 1 = 12.00
        # Negative Marks: 3 * 0.25 = 0.75
        # Final Score: 12.00 - 0.75 = 11.25
        self.assertEqual(finalized.score, Decimal("11.25"))

        # Score %: (11.25 / 16.00) * 100 = 70.3125% -> 70.31%
        self.assertEqual(finalized.percentage, Decimal("70.31"))

        # Result Model Verification
        result = Result.objects.get(attempt=finalized)
        self.assertEqual(result.total_questions, 16)
        self.assertEqual(result.correct_answers, 12)
        self.assertEqual(result.incorrect_answers, 3)
        self.assertEqual(result.skipped_answers, 1)
        self.assertEqual(result.positive_marks, Decimal("12.00"))
        self.assertEqual(result.negative_marks, Decimal("0.75"))
        self.assertEqual(result.final_score, Decimal("11.25"))
        self.assertEqual(result.maximum_score, Decimal("16.00"))
        self.assertEqual(result.score_percentage, Decimal("70.31"))

        # Accuracy %: (12 / 15) * 100 = 80.00%
        self.assertEqual(result.accuracy_percentage, Decimal("80.00"))

        # Completion %: (15 / 16) * 100 = 93.75%
        self.assertEqual(result.completion_percentage, Decimal("93.75"))

        # Performance Level: 70-79.99% -> GOOD
        self.assertEqual(result.performance_level, Result.Level.GOOD)

    def test_question_bank_shortage_error_when_fewer_than_16_questions(self):
        """Verifies that QuestionBankShortageError is raised if fewer than 16 verified questions exist."""
        # Seed only 10 questions
        self._seed_16_verified_questions(10)

        with self.assertRaises(QuestionBankShortageError) as ctx:
            QuestionRepetitionEngine.select_topic_examination_questions(
                user=self.user,
                examination=self.exam,
                attempt_number=1,
                random_seed="test-seed"
            )

        err = ctx.exception
        self.assertEqual(err.available, 10)
        self.assertEqual(err.required, 16)
        self.assertIn("Question bank shortage", str(err))

    def test_anti_repetition_and_candidate_exposure_history(self):
        """Verifies candidate exposure history tracking across subsequent attempts."""
        self._seed_16_verified_questions(16)

        # Attempt 1
        att1, _ = ExamEvaluationService.start_or_resume_attempt(self.user, self.exam)
        self.assertEqual(UserQuestionHistory.objects.filter(user=self.user, examination=self.exam).count(), 16)
        ExamEvaluationService.finalize_submission(att1)

        # Attempt 2
        att2, _ = ExamEvaluationService.start_or_resume_attempt(self.user, self.exam)
        self.assertEqual(att2.attempt_number, 2)
        # All 16 questions should be distinct in attempt 2
        self.assertEqual(len(set(att2.ordered_question_ids)), 16)
        ExamEvaluationService.finalize_submission(att2)

    def test_server_enforced_5_attempts_limit(self):
        """Verifies that exactly 5 attempts are permitted, and 6th attempt is blocked on server."""
        self._seed_16_verified_questions(16)

        for i in range(1, 6):
            att, _ = ExamEvaluationService.start_or_resume_attempt(self.user, self.exam)
            self.assertEqual(att.attempt_number, i)
            ExamEvaluationService.finalize_submission(att)

        # 6th attempt must be rejected with PermissionError
        with self.assertRaises(PermissionError) as ctx:
            ExamEvaluationService.start_or_resume_attempt(self.user, self.exam)

        self.assertIn("maximum allowed limit of 5 attempts", str(ctx.exception))

    def test_topic_learning_notes_view(self):
        """Verifies topic learning notes view renders concept understanding, examples, and formulas."""
        from assessments.question_engine import generate_learning_notes_for_topic
        notes_data = generate_learning_notes_for_topic("Mathematics", "Matrices and Determinants")
        LearningNote.objects.create(
            topic=self.topic,
            subject=self.subject,
            concept_summary=notes_data["concept_summary"],
            detailed_explanation=notes_data["detailed_explanation"],
            real_world_applications=notes_data["real_world_applications"],
            advantages_disadvantages=notes_data["advantages_disadvantages"],
            comparison_table_markdown=notes_data["comparison_table_markdown"],
            common_pitfalls=notes_data["common_pitfalls"],
            examples_json=notes_data["examples_json"],
            quick_revision_formulas=notes_data["quick_revision_formulas"],
            practice_questions_json=notes_data["practice_questions_json"],
        )

        url = reverse("topic_learning_notes", kwargs={"topic_id": self.topic.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Concept Understanding")
        self.assertContains(response, "Quick Revision Formulas")
        self.assertContains(response, "Take Topic Examination")

    def test_performance_analytics_dashboard_view(self):
        """Verifies performance analytics dashboard renders average metrics and subject mastery."""
        url = reverse("performance_analytics")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Performance Analytics & Target Gap Engine")
        self.assertIn("subject_analytics", response.context)
        self.assertIn("personal_target", response.context)

    def test_prevent_duplicate_attempt_creation_and_resume_active(self):
        """
        Critical Bug Fix Verification (Section 3):
        Verifies that repeated start requests for the same active exam resume the attempt
        instead of violating the unique_user_exam_attempt_number constraint.
        """
        self._seed_16_verified_questions(16)
        att1, created1 = ExamEvaluationService.start_or_resume_attempt(self.user, self.exam)
        self.assertTrue(created1)
        self.assertEqual(att1.attempt_number, 1)
        self.assertEqual(att1.status, ExamAttempt.Status.IN_PROGRESS)

        # Second call for the same active exam
        att2, created2 = ExamEvaluationService.start_or_resume_attempt(self.user, self.exam)
        self.assertFalse(created2)
        self.assertEqual(att2.id, att1.id)
        self.assertEqual(att2.attempt_number, 1)
        self.assertEqual(ExamAttempt.objects.filter(user=self.user, examination=self.exam).count(), 1)

    def test_next_attempt_increment_and_max_5_attempts_limit(self):
        """
        Verifies attempt lifecycle: completion increments attempt_number up to max 5,
        and strictly blocks attempt 6 on server side.
        """
        self._seed_16_verified_questions(16)
        for i in range(1, 6):
            att, created = ExamEvaluationService.start_or_resume_attempt(self.user, self.exam)
            self.assertEqual(att.attempt_number, i)
            # Finalize submission to complete this attempt
            ExamEvaluationService.finalize_submission(att)

        # 6th attempt must be rejected with PermissionError
        with self.assertRaises(PermissionError):
            ExamEvaluationService.start_or_resume_attempt(self.user, self.exam)

    def test_canonical_section_5_1_examination_routes(self):
        """
        Verifies all 7 canonical Section 5.1 examination routes return HTTP 200.
        """
        self.client.force_login(self.user)
        test_routes = [
            "/assessments/entrance/",
            "/assessments/exams/",
            "/assessments/entrance/chapters/",
            "/assessments/entrance/practice/",
            "/assessments/entrance/mock-test/",
            "/assessments/entrance/results/",
            "/assessments/entrance/analytics/",
        ]
        for route in test_routes:
            resp = self.client.get(route)
            self.assertEqual(resp.status_code, 200, f"Route '{route}' failed with status {resp.status_code}")



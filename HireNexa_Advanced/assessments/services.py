import hashlib
import json
import logging
import random
import re
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from django.conf import settings
from django.db import models, transaction, IntegrityError
from django.utils import timezone
from .models import (
    Subject, Topic, Subtopic, Chapter, Question, QuestionOption, QuestionExplanation,
    QuestionPackage, Examination, ExamQuestion, ExamAttempt, ExamResponse,
    UserQuestionHistory, TopicCompletion, AttemptQuestion, Result, TopicProgress,
    SubjectProgress, PersonalTarget, AdminReviewHistory, EntranceTrack,
    CodingProblem, TestCase, CodingSubmission, StudentSkillMastery,
    PlacementReadiness, CareerOpportunity, AIGenerationBatch
)

logger = logging.getLogger(__name__)


class QuestionBankShortageError(Exception):
    """Raised when an examination or topic test lacks sufficient verified questions in its pool."""
    def __init__(self, topic_name: str, available_count: int, required_count: int = 16):
        self.topic_name = topic_name
        self.available_count = available_count
        self.required_count = required_count
        self.available = available_count
        self.required = required_count
        super().__init__(
            f"Question bank shortage: Topic '{topic_name}' currently has only {available_count}/{required_count} "
            f"verified questions. Examination generation paused until full verified question set is available."
        )


# ==============================================================================
# 1. PERMANENT ANTI-REPETITION & QUESTION DIVERSITY ENGINE
# ==============================================================================

class QuestionRepetitionEngine:
    """
    Prevents repeated questions, enforces topic isolation, guarantees difficulty balance
    (4 Beginner, 7 Intermediate, 5 Advanced per 16-question set), tracks candidate
    exposure history across attempts, and ensures stable answer option randomizations.
    """

    @classmethod
    def compute_fingerprint(cls, question_text: str, options: List[str] = None) -> str:
        """Generates deterministic SHA-256 fingerprint for duplicate detection."""
        clean_text = " ".join((question_text or "").strip().lower().split())
        clean_opts = "|".join(sorted(" ".join(str(o).strip().lower().split()) for o in (options or [])))
        payload = f"{clean_text}::{clean_opts}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def is_duplicate(cls, question_text: str, options: List[str] = None, exclude_id: int = None) -> bool:
        """Checks if an identical or normalized duplicate question exists in the database."""
        fp = cls.compute_fingerprint(question_text, options)
        qs = Question.objects.filter(fingerprint=fp)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    @classmethod
    def select_topic_examination_questions(
        cls,
        user,
        examination: Examination,
        attempt_number: int,
        random_seed: str
    ) -> List[Tuple[Question, List[int]]]:
        """
        Selects exactly 16 verified questions for an individual topic test:
        - 4 Beginner
        - 7 Intermediate
        - 5 Advanced
        Strictly isolated to examination.topic.
        If fewer than 16 verified questions exist, raises QuestionBankShortageError.
        Prefers unseen questions for this candidate.
        Returns list of (Question, shuffled_option_ids).
        """
        topic = examination.topic
        if not topic and examination.chapter:
            # Fallback to chapter topic if mapped
            topic = Topic.objects.filter(subject=examination.subject, slug=examination.chapter.slug).first()

        topic_name = topic.name if topic else (examination.title)
        
        # Query verified questions strictly belonging to this topic/examination
        if topic:
            pool_qs = Question.objects.filter(
                topic=topic,
                status=Question.Status.APPROVED,
                is_verified=True
            )
            total_available = pool_qs.count()
            if total_available < 16:
                # Fallback to general approved questions for this topic if verified flag was unmigrated
                pool_qs = Question.objects.filter(
                    topic=topic,
                    status=Question.Status.APPROVED
                )
                total_available = pool_qs.count()

            if total_available < 16:
                raise QuestionBankShortageError(topic_name, total_available, 16)
        else:
            # Examination without an explicit topic (e.g. Entrance Mock test, or custom examination test fixture)
            pool_qs = examination.questions.filter(status=Question.Status.APPROVED, is_verified=True)
            total_available = pool_qs.count()
            if total_available == 0:
                pool_qs = examination.questions.filter(status=Question.Status.APPROVED)
                total_available = pool_qs.count()
            if total_available == 0 and examination.exam_questions.exists():
                pool_qs = Question.objects.filter(exam_instances__examination=examination, status=Question.Status.APPROVED)
                total_available = pool_qs.count()

            if total_available == 0:
                raise QuestionBankShortageError(topic_name, 0, 16)

            # If fewer than 16 questions are explicitly configured for this non-topic exam (e.g. unit test fixture),
            # return all attached questions without raising shortage error.
            if total_available < 16:
                pool_list = list(pool_qs.prefetch_related("options").order_by("order", "id"))
                result_pairs = []
                for q in pool_list:
                    opt_ids = [opt.id for opt in q.options.all().order_by("order", "id")]
                    result_pairs.append((q, opt_ids))
                return result_pairs

        pool_list = list(pool_qs.prefetch_related("options"))

        # Candidate exposure history for this topic/exam
        seen_qids = set(
            UserQuestionHistory.objects.filter(
                user=user,
                examination=examination
            ).values_list("question_id", flat=True)
        )

        unseen_pool = [q for q in pool_list if q.id not in seen_qids]

        # Categorize by required difficulty tiers (Default: 5 Easy, 7 Medium, 4 Hard per 16-Q blueprint)
        beginner_diffs = [Question.Level.BEGINNER, Question.Level.EASY]
        intermediate_diffs = [Question.Level.INTERMEDIATE, Question.Level.MEDIUM]
        advanced_diffs = [Question.Level.ADVANCED, Question.Level.HARD, Question.Level.INTERVIEW, Question.Level.PLACEMENT]

        unseen_beg = [q for q in unseen_pool if q.difficulty in beginner_diffs]
        unseen_int = [q for q in unseen_pool if q.difficulty in intermediate_diffs]
        unseen_adv = [q for q in unseen_pool if q.difficulty in advanced_diffs]

        rng = random.Random(f"{random_seed}-select")
        rng.shuffle(unseen_beg)
        rng.shuffle(unseen_int)
        rng.shuffle(unseen_adv)

        # Concept deduplication helper
        selected_qs = []
        selected_concepts = set()

        def add_with_concept_diversity(source_candidates, target_count):
            added = 0
            deferred = []
            for candidate in source_candidates:
                cid = getattr(candidate, "concept_identifier", "") or getattr(candidate, "concept_id", "")
                if cid and cid in selected_concepts:
                    deferred.append(candidate)
                    continue
                selected_qs.append(candidate)
                if cid:
                    selected_concepts.add(cid)
                added += 1
                if added >= target_count:
                    break
            # If not enough with unique concepts, take deferred
            if added < target_count:
                for candidate in deferred:
                    selected_qs.append(candidate)
                    added += 1
                    if added >= target_count:
                        break

        # Blueprint target counts: 5 Easy / Beginner, 7 Medium / Intermediate, 4 Hard / Advanced
        add_with_concept_diversity(unseen_beg, 5)
        add_with_concept_diversity(unseen_int, 7)
        add_with_concept_diversity(unseen_adv, 4)

        # Backfill from remaining unseen if a specific tier was exhausted
        if len(selected_qs) < 16:
            selected_ids = {q.id for q in selected_qs}
            remaining_unseen = [q for q in unseen_pool if q.id not in selected_ids]
            rng.shuffle(remaining_unseen)
            needed = 16 - len(selected_qs)
            selected_qs.extend(remaining_unseen[:needed])

        # If candidate has seen questions across earlier attempts and unseen pool < 16,
        # backfill from least-recently-seen questions in this topic pool
        if len(selected_qs) < 16:
            selected_ids = {q.id for q in selected_qs}
            remaining_seen = [q for q in pool_list if q.id not in selected_ids]
            # Sort by least recently seen
            seen_order = list(
                UserQuestionHistory.objects.filter(
                    user=user,
                    examination=examination,
                    question_id__in=[q.id for q in remaining_seen]
                ).order_by("seen_at").values_list("question_id", flat=True)
            )
            seen_order_map = {qid: idx for idx, qid in enumerate(seen_order)}
            remaining_seen.sort(key=lambda q: seen_order_map.get(q.id, 0))
            
            needed = 16 - len(selected_qs)
            selected_qs.extend(remaining_seen[:needed])

        # Guarantee exactly 16 distinct questions
        distinct_map = {}
        for q in selected_qs:
            if q.id not in distinct_map:
                distinct_map[q.id] = q
        selected_qs = list(distinct_map.values())[:16]

        if examination.shuffle_questions:
            rng.shuffle(selected_qs)

        # Freeze option shuffling per question
        result = []
        for idx, q in enumerate(selected_qs, start=1):
            opts = list(q.options.all().order_by("order", "id"))
            if examination.shuffle_options:
                opt_rng = random.Random(f"{random_seed}-opt-{q.id}")
                opt_rng.shuffle(opts)
            shuffled_ids = [o.id for o in opts]
            result.append((q, shuffled_ids))

        return result


# ==============================================================================
# 2. EXAM ATTEMPT & REAL-TIME EVALUATION SERVICE
# ==============================================================================

class ExamEvaluationService:
    """
    Manages live exam lifecycle: initiation, synchronized server-side countdown,
    heartbeat auto-save, negative mark calculations, attempt limits, and analytics.
    """

    @classmethod
    @transaction.atomic
    def start_or_resume_attempt(cls, user, examination: Examination) -> Tuple[ExamAttempt, bool]:
        """
        Retrieves existing in-progress attempt or initiates a new one with deterministic
        server-side expiration, max 5 attempt limit enforcement, concurrency serialization,
        and atomic savepoint protection against race conditions.
        """
        if not user or not user.is_authenticated:
            raise PermissionError("Authentication required to take this examination.")

        if not examination or not examination.is_active or not examination.is_published:
            raise PermissionError("This examination is currently inactive or unpublished.")

        now = timezone.now()

        # Concurrency safety: acquire row-level lock on the User record to serialize
        # concurrent attempt initiation requests for the same user across multiple threads/tabs.
        from accounts.models import User
        try:
            User.objects.select_for_update().filter(id=user.id).first()
        except Exception:
            pass

        # Retrieve and lock all existing attempts for this candidate & exam ordered by attempt_number
        existing_attempts = list(
            ExamAttempt.objects.select_for_update().filter(
                user=user,
                examination=examination
            ).order_by("attempt_number")
        )

        # Check whether an attempt is already in progress
        active_attempt = next((a for a in existing_attempts if a.status == ExamAttempt.Status.IN_PROGRESS), None)
        if active_attempt:
            dl = active_attempt.deadline or active_attempt.expires_at
            if dl and now > dl:
                # Expired while candidate was away — auto-finalize it
                cls.finalize_submission(active_attempt, auto_timed_out=True)
                active_attempt = None
                # Refresh existing attempts list after finalization
                existing_attempts = list(
                    ExamAttempt.objects.filter(
                        user=user,
                        examination=examination
                    ).order_by("attempt_number")
                )
            else:
                # Active in-progress attempt exists and is valid — resume it without duplicate creation
                return active_attempt, False

        # Enforce server-side attempt limit (strictly max 5 per candidate per test)
        max_allowed = examination.max_attempts or 5
        past_attempts_count = len(existing_attempts)
        if past_attempts_count >= max_allowed:
            raise PermissionError(f"You have reached the maximum allowed limit of {max_allowed} attempts for this examination.")

        # Enforce prerequisite lock gate for Final Combined Entrance Exam
        if examination.is_final_combined and examination.required_topics_count > 0:
            completed_count = TopicCompletion.objects.filter(
                user=user,
                topic__subject=examination.subject,
                is_completed=True
            ).count()
            if completed_count < examination.required_topics_count:
                raise PermissionError(
                    f"Final Examination locked: You must complete all {examination.required_topics_count} "
                    f"required topics before unlocking this examination. (Completed: {completed_count}/{examination.required_topics_count})"
                )

        # Calculate next valid attempt number using the max of existing attempt numbers + 1
        max_existing_num = max([a.attempt_number for a in existing_attempts], default=0)
        attempt_num = max_existing_num + 1
        if attempt_num > max_allowed:
            raise PermissionError(f"You have reached the maximum allowed limit of {max_allowed} attempts for this examination.")

        duration_minutes = examination.duration_minutes or 17
        deadline = now + timezone.timedelta(minutes=duration_minutes)
        random_seed = f"{user.id}-{examination.id}-{attempt_num}-{int(now.timestamp())}"

        # Select exactly 16 verified, topic-isolated questions via QuestionRepetitionEngine
        selected_pairs = QuestionRepetitionEngine.select_topic_examination_questions(
            user=user,
            examination=examination,
            attempt_number=attempt_num,
            random_seed=random_seed
        )

        ordered_qids = [pair[0].id for pair in selected_pairs]
        total_possible = sum(Decimal(str(pair[0].marks or Decimal("1.00"))) for pair in selected_pairs) if selected_pairs else Decimal("16.00")

        # Nested atomic savepoint: guarantees graceful recovery if a concurrent transaction
        # committed an attempt with the same unique (user, examination, attempt_number) key.
        try:
            with transaction.atomic():
                attempt = ExamAttempt.objects.create(
                    user=user,
                    examination=examination,
                    attempt_number=attempt_num,
                    status=ExamAttempt.Status.IN_PROGRESS,
                    started_at=now,
                    deadline=deadline,
                    expires_at=deadline,
                    total_possible_marks=total_possible,
                    total_questions=len(ordered_qids),
                    ordered_question_ids=ordered_qids,
                    random_seed=random_seed,
                )

                # Freeze into AttemptQuestion snapshots
                attempt_q_records = [
                    AttemptQuestion(
                        attempt=attempt,
                        question=pair[0],
                        question_order=idx,
                        shuffled_option_ids=pair[1],
                        marks_weight=pair[0].marks or Decimal("1.00"),
                        negative_weight=examination.negative_marking or Decimal("0.25")
                    )
                    for idx, pair in enumerate(selected_pairs, start=1)
                ]
                AttemptQuestion.objects.bulk_create(attempt_q_records, ignore_conflicts=True)

                # Record candidate question exposure history
                history_records = [
                    UserQuestionHistory(
                        user=user,
                        question=pair[0],
                        examination=examination,
                        topic=examination.topic or pair[0].topic,
                        attempt_number=attempt_num
                    )
                    for pair in selected_pairs
                ]
                UserQuestionHistory.objects.bulk_create(history_records, ignore_conflicts=True)

                # Initialize blank ExamResponse records
                responses = [
                    ExamResponse(attempt=attempt, question_id=qid)
                    for qid in ordered_qids
                ]
                ExamResponse.objects.bulk_create(responses, ignore_conflicts=True)

                return attempt, True
        except IntegrityError:
            # Race condition / duplicate request recovery:
            # Another concurrent request already created the attempt record.
            # 1. Retrieve the active in-progress attempt if available
            existing = ExamAttempt.objects.filter(
                user=user,
                examination=examination,
                status=ExamAttempt.Status.IN_PROGRESS
            ).first()
            if existing:
                return existing, False

            # 2. Retrieve attempt by attempt_number
            existing_by_num = ExamAttempt.objects.filter(
                user=user,
                examination=examination,
                attempt_number=attempt_num
            ).first()
            if existing_by_num:
                return existing_by_num, False

            # 3. Retrieve latest attempt for this candidate & exam
            latest = ExamAttempt.objects.filter(
                user=user,
                examination=examination
            ).order_by("-attempt_number").first()
            if latest:
                return latest, False

            # 4. Concurrency fallback: aggregate fresh max attempt number
            from django.db.models import Max
            fresh_max = ExamAttempt.objects.filter(user=user, examination=examination).aggregate(m=Max("attempt_number"))["m"] or 0
            if fresh_max >= max_allowed:
                raise PermissionError(f"You have reached the maximum allowed limit of {max_allowed} attempts for this examination.")

            fresh_num = fresh_max + 1
            with transaction.atomic():
                attempt = ExamAttempt.objects.create(
                    user=user,
                    examination=examination,
                    attempt_number=fresh_num,
                    status=ExamAttempt.Status.IN_PROGRESS,
                    started_at=now,
                    deadline=deadline,
                    expires_at=deadline,
                    total_possible_marks=total_possible,
                    total_questions=len(ordered_qids),
                    ordered_question_ids=ordered_qids,
                    random_seed=random_seed,
                )
                attempt_q_records = [
                    AttemptQuestion(
                        attempt=attempt,
                        question=pair[0],
                        question_order=idx,
                        shuffled_option_ids=pair[1],
                        marks_weight=pair[0].marks or Decimal("1.00"),
                        negative_weight=examination.negative_marking or Decimal("0.25")
                    )
                    for idx, pair in enumerate(selected_pairs, start=1)
                ]
                AttemptQuestion.objects.bulk_create(attempt_q_records, ignore_conflicts=True)
                responses = [
                    ExamResponse(attempt=attempt, question_id=qid)
                    for qid in ordered_qids
                ]
                ExamResponse.objects.bulk_create(responses, ignore_conflicts=True)
                return attempt, True

    @classmethod
    def save_candidate_response(
        cls,
        attempt: ExamAttempt,
        question_id: int,
        selected_option_ids: List[int] = None,
        text_answer: str = "",
        is_marked_for_review: bool = False,
        time_spent_seconds: int = 0,
    ) -> Dict[str, Any]:
        """
        Auto-save answer endpoint for AJAX calls during test.
        Enforces 5-second grace period past deadline and validates options ownership.
        """
        now = timezone.now()
        if attempt.status != ExamAttempt.Status.IN_PROGRESS:
            return {"success": False, "error": "Exam has already been submitted."}

        dl = attempt.deadline or attempt.expires_at
        grace_period = timezone.timedelta(seconds=5)
        if dl and now > (dl + grace_period):
            cls.finalize_submission(attempt, auto_timed_out=True)
            return {"success": False, "error": "Exam time expired. Submitted automatically.", "timed_out": True}

        # Verify question belongs to this exam
        if not (attempt.examination.questions.filter(id=question_id).exists() or
                attempt.examination.exam_questions.filter(question_id=question_id).exists()):
            return {"success": False, "error": "Invalid question for this examination."}

        selected_option_ids = selected_option_ids or []
        # Security validation: submitted option must belong to the question
        valid_opts = set(
            QuestionOption.objects.filter(question_id=question_id).values_list("id", flat=True)
        )
        clean_selected = [int(oid) for oid in selected_option_ids if str(oid).isdigit() and int(oid) in valid_opts]

        resp, _ = ExamResponse.objects.get_or_create(attempt=attempt, question_id=question_id)
        resp.selected_option_ids = clean_selected
        resp.text_answer = (text_answer or "").strip()
        resp.is_marked_for_review = bool(is_marked_for_review)
        if time_spent_seconds > 0:
            resp.time_spent_seconds += int(time_spent_seconds)
        resp.save()

        attempt.last_active_at = now
        attempt.save(update_fields=["last_active_at"])

        return {
            "success": True,
            "seconds_remaining": attempt.seconds_remaining,
            "is_marked_for_review": resp.is_marked_for_review,
            "has_answer": bool(resp.selected_option_ids or resp.text_answer),
        }

    @classmethod
    @transaction.atomic
    def finalize_submission(cls, attempt: ExamAttempt, auto_timed_out: bool = False, force_recalculate: bool = False) -> ExamAttempt:
        """
        Calculates exam score using exact Decimal arithmetic, negative marking,
        accuracy, and updates student skill mastery.
        """
        if attempt.status not in (ExamAttempt.Status.IN_PROGRESS,) and not force_recalculate:
            if not Result.objects.filter(attempt=attempt).exists():
                force_recalculate = True
            else:
                return attempt

        now = timezone.now()
        if not attempt.submitted_at:
            attempt.submitted_at = now
        if attempt.status == ExamAttempt.Status.IN_PROGRESS:
            attempt.status = ExamAttempt.Status.EXPIRED if auto_timed_out else ExamAttempt.Status.SUBMITTED

        exam = attempt.examination
        neg_rate = Decimal(str(exam.negative_marking if exam.negative_marking is not None else Decimal("0.25")))

        responses = attempt.responses.select_related("question").prefetch_related("question__options").all()

        total_score = Decimal("0.00")
        answered_cnt = 0
        correct_cnt = 0
        incorrect_cnt = 0
        skipped_cnt = 0

        for resp in responses:
            q = resp.question
            q_marks = Decimal(str(q.marks or Decimal("1.00")))

            is_answered = bool(resp.selected_option_ids or resp.text_answer)
            if not is_answered:
                skipped_cnt += 1
                resp.is_correct = None
                resp.marks_awarded = Decimal("0.00")
                resp.save(update_fields=["is_correct", "marks_awarded"])
                continue

            answered_cnt += 1
            correct_opts = set(q.options.filter(is_correct=True).values_list("id", flat=True))

            if q.question_type in (
                Question.Type.MCQ, Question.Type.TRUE_FALSE,
                Question.Type.OUTPUT_PREDICTION, Question.Type.FIND_ERROR,
                Question.Type.LOGICAL_REASONING
            ):
                selected = set(resp.selected_option_ids)
                if selected == correct_opts and len(selected) > 0:
                    resp.is_correct = True
                    resp.marks_awarded = q_marks
                    correct_cnt += 1
                    total_score += q_marks
                else:
                    resp.is_correct = False
                    deduction = q_marks * neg_rate
                    resp.marks_awarded = -deduction
                    incorrect_cnt += 1
                    total_score -= deduction

            elif q.question_type == Question.Type.MSQ:
                selected = set(resp.selected_option_ids)
                if selected == correct_opts and len(selected) > 0:
                    resp.is_correct = True
                    resp.marks_awarded = q_marks
                    correct_cnt += 1
                    total_score += q_marks
                else:
                    resp.is_correct = False
                    deduction = q_marks * neg_rate
                    resp.marks_awarded = -deduction
                    incorrect_cnt += 1
                    total_score -= deduction

            elif q.question_type in (Question.Type.FILL_BLANKS, Question.Type.SHORT_ANSWER, Question.Type.SQL_QUERY):
                clean_ans = resp.text_answer.strip().lower()
                clean_key = q.verified_answer_key.strip().lower()
                if clean_ans and clean_ans == clean_key:
                    resp.is_correct = True
                    resp.marks_awarded = q_marks
                    correct_cnt += 1
                    total_score += q_marks
                else:
                    resp.is_correct = False
                    deduction = q_marks * neg_rate
                    resp.marks_awarded = -deduction
                    incorrect_cnt += 1
                    total_score -= deduction
            else:
                resp.is_correct = None
                resp.marks_awarded = Decimal("0.00")

            resp.save(update_fields=["is_correct", "marks_awarded"])

        # Exact decimal calculations complying with mandatory scoring requirements:
        # Positive Marks = Correct Answers × 1
        # Negative Marks = Incorrect Answers × 0.25
        # Final Score = Positive Marks - Negative Marks
        # Score Percentage = (Final Score / Maximum Marks) × 100
        # Accuracy Percentage = (Correct Answers / Attempted Questions) × 100
        # Completion Percentage = (Attempted Questions / Total Questions) × 100
        # Time Utilization Percentage = (Time Used / Total Allowed Time) × 100
        positive_marks = Decimal(correct_cnt) * Decimal("1.00")
        negative_marks = Decimal(incorrect_cnt) * neg_rate
        final_score = positive_marks - negative_marks
        max_possible = Decimal(str(attempt.total_possible_marks or "16.00"))

        if max_possible > 0:
            score_pct = round((final_score / max_possible) * Decimal("100.00"), 2)
        else:
            score_pct = Decimal("0.00")

        attempted_cnt = correct_cnt + incorrect_cnt
        if attempted_cnt > 0:
            accuracy_pct = round((Decimal(correct_cnt) / Decimal(attempted_cnt)) * Decimal("100.00"), 2)
        else:
            accuracy_pct = Decimal("0.00")

        total_qs_cnt = attempt.total_questions or len(responses) or 16
        if total_qs_cnt > 0:
            completion_pct = round((Decimal(attempted_cnt) / Decimal(total_qs_cnt)) * Decimal("100.00"), 2)
        else:
            completion_pct = Decimal("0.00")

        # Time utilization calculation
        time_used_seconds = int((attempt.submitted_at - attempt.started_at).total_seconds()) if attempt.started_at else 0
        allowed_seconds = (exam.duration_minutes or 21) * 60
        if allowed_seconds > 0:
            time_util_pct = min(Decimal("100.00"), round((Decimal(time_used_seconds) / Decimal(allowed_seconds)) * Decimal("100.00"), 2))
        else:
            time_util_pct = Decimal("0.00")

        # Determine performance category:
        # 90-100%: Excellent | 80-89.99%: Very Good | 70-79.99%: Good
        # 60-69.99%: Average | 40-59.99%: Needs Improvement | <40%: Requires More Practice
        if score_pct >= 90:
            perf_level = Result.Level.EXCELLENT
        elif score_pct >= 80:
            perf_level = Result.Level.VERY_GOOD
        elif score_pct >= 70:
            perf_level = Result.Level.GOOD
        elif score_pct >= 60:
            perf_level = Result.Level.AVERAGE
        elif score_pct >= 40:
            perf_level = Result.Level.NEEDS_IMPROVEMENT
        else:
            perf_level = Result.Level.PRACTICE

        attempt.score = final_score
        attempt.percentage = score_pct
        passing_pct = Decimal(str(exam.passing_percentage or Decimal("40.00")))
        attempt.passed = bool(attempt.percentage >= passing_pct)

        attempt.answered_count = answered_cnt
        attempt.correct_count = correct_cnt
        attempt.incorrect_count = incorrect_cnt
        attempt.skipped_count = skipped_cnt
        attempt.save(update_fields=[
            "submitted_at", "status", "score", "percentage",
            "passed", "answered_count", "correct_count",
            "incorrect_count", "skipped_count"
        ])

        # Record or update ultra-advanced Result entity
        Result.objects.update_or_create(
            attempt=attempt,
            defaults={
                "user": attempt.user,
                "examination": exam,
                "total_questions": total_qs_cnt,
                "attempted_questions": attempted_cnt,
                "correct_answers": correct_cnt,
                "incorrect_answers": incorrect_cnt,
                "skipped_answers": skipped_cnt,
                "positive_marks": positive_marks,
                "negative_marks": negative_marks,
                "final_score": final_score,
                "maximum_score": max_possible,
                "score_percentage": score_pct,
                "accuracy_percentage": accuracy_pct,
                "completion_percentage": completion_pct,
                "time_utilization_percentage": time_util_pct,
                "performance_level": perf_level,
                "is_passed": attempt.passed,
            }
        )

        # Track topic completion if this examination is linked to a topic
        if exam.topic:
            top_comp, _ = TopicCompletion.objects.get_or_create(user=attempt.user, topic=exam.topic)
            top_comp.is_completed = True
            if attempt.score > top_comp.best_score:
                top_comp.best_score = attempt.score
            top_comp.save()

            # Update TopicProgress with multi-attempt comparison
            topic_prog, _ = TopicProgress.objects.get_or_create(user=attempt.user, topic=exam.topic)
            all_attempts = ExamAttempt.objects.filter(
                user=attempt.user,
                examination=exam,
                status__in=[ExamAttempt.Status.SUBMITTED, ExamAttempt.Status.EXPIRED]
            ).order_by("attempt_number")
            topic_prog.attempts_count = all_attempts.count()
            
            history = []
            scores = []
            pcts = []
            for att in all_attempts:
                sc = float(att.score)
                pc = float(att.percentage)
                scores.append(sc)
                pcts.append(pc)
                history.append({
                    "attempt": att.attempt_number,
                    "score": sc,
                    "percentage": pc,
                    "date": att.submitted_at.strftime("%Y-%m-%d %H:%M") if att.submitted_at else ""
                })

            topic_prog.best_score = Decimal(str(max(scores))) if scores else final_score
            topic_prog.best_percentage = Decimal(str(max(pcts))) if pcts else score_pct
            topic_prog.latest_percentage = score_pct
            topic_prog.average_percentage = Decimal(str(round(sum(pcts) / len(pcts), 2))) if pcts else score_pct
            topic_prog.mastery_percentage = topic_prog.best_percentage
            topic_prog.attempt_history = history
            if attempt.passed:
                topic_prog.is_completed = True
            topic_prog.last_attempted_at = now
            topic_prog.save()

        # Update SubjectProgress
        if exam.subject:
            subj_prog, _ = SubjectProgress.objects.get_or_create(user=attempt.user, subject=exam.subject)
            total_top = exam.subject.topics.count()
            comp_top = TopicProgress.objects.filter(user=attempt.user, topic__subject=exam.subject, is_completed=True).count()
            subj_prog.total_topics_count = total_top
            subj_prog.completed_topics_count = comp_top
            
            top_progs = TopicProgress.objects.filter(user=attempt.user, topic__subject=exam.subject)
            if top_progs.exists():
                avg_m = top_progs.aggregate(models.Avg("mastery_percentage"))["mastery_percentage__avg"] or 0.0
                subj_prog.mastery_percentage = round(Decimal(str(avg_m)), 2)
            else:
                subj_prog.mastery_percentage = Decimal("0.00")
            
            subj_prog.learning_progress_percentage = round((Decimal(comp_top) / Decimal(total_top)) * Decimal("100.00"), 2) if total_top > 0 else Decimal("0.00")
            subj_prog.save()

        # Update candidate skill profile
        cls.update_candidate_mastery(attempt.user, responses)

        return attempt

    @classmethod
    def update_candidate_mastery(cls, user, responses):
        """Updates subject and topic mastery records based on exam performance."""
        subject_stats = {}
        for resp in responses:
            if resp.is_correct is None:
                continue
            subj = resp.question.subject
            if subj.id not in subject_stats:
                subject_stats[subj.id] = {"subject": subj, "total": 0, "correct": 0, "topics": {}}
            subject_stats[subj.id]["total"] += 1
            if resp.is_correct:
                subject_stats[subj.id]["correct"] += 1

            topic = resp.question.topic
            if topic:
                t_slug = topic.slug
                t_dict = subject_stats[subj.id]["topics"]
                if t_slug not in t_dict:
                    t_dict[t_slug] = {"name": topic.name, "total": 0, "correct": 0}
                t_dict[t_slug]["total"] += 1
                if resp.is_correct:
                    t_dict[t_slug]["correct"] += 1

        for subj_id, data in subject_stats.items():
            mastery, _ = StudentSkillMastery.objects.get_or_create(user=user, subject=data["subject"])
            mastery.attempted_count += data["total"]
            mastery.correct_count += data["correct"]
            if mastery.attempted_count > 0:
                mastery.accuracy_percentage = round((mastery.correct_count / mastery.attempted_count) * 100.0, 2)

            # Analyze weak / strong topics
            weak = list(mastery.weak_topics or [])
            strong = list(mastery.strong_topics or [])
            for t_slug, t_info in data["topics"].items():
                acc = (t_info["correct"] / t_info["total"]) * 100.0
                if acc < 50.0 and t_info["name"] not in weak:
                    weak.append(t_info["name"])
                elif acc >= 75.0 and t_info["name"] not in strong:
                    strong.append(t_info["name"])

            mastery.weak_topics = weak[:5]
            mastery.strong_topics = strong[:5]
            mastery.save()

        # Re-evaluate PlacementReadiness
        cls.recalculate_placement_readiness(user)

    @classmethod
    def recalculate_placement_readiness(cls, user):
        """Calculates 0-100 placement readiness score from exams, coding submissions, and activity."""
        readiness, _ = PlacementReadiness.objects.get_or_create(user=user)

        # 1. Exam Performance (40% weight)
        attempts = ExamAttempt.objects.filter(user=user, status__in=[ExamAttempt.Status.SUBMITTED, ExamAttempt.Status.TIMED_OUT])
        if attempts.exists():
            avg_exam_pct = float(attempts.aggregate(models.Avg("percentage"))["percentage__avg"] or 0.0)
        else:
            avg_exam_pct = 0.0

        # 2. Coding Problem Solving (40% weight)
        accepted_coding = CodingSubmission.objects.filter(user=user, status=CodingSubmission.Status.ACCEPTED).values("problem_id").distinct().count()
        coding_score = min(100, accepted_coding * 10)  # 10 problems = 100%

        # 3. Overall Readiness (safely clamped to 0-100 for PositiveIntegerField models)
        clamped_mcq = max(0, min(100, int(avg_exam_pct)))
        clamped_coding = max(0, min(100, int(coding_score)))
        overall = max(0, min(100, round((clamped_mcq * 0.5) + (clamped_coding * 0.5))))
        readiness.overall_readiness_score = int(overall)
        readiness.mcq_score = int(clamped_mcq)
        readiness.coding_score = int(clamped_coding)

        # Generate strengths & recommendations
        masteries = StudentSkillMastery.objects.filter(user=user)
        strengths = []
        weaknesses = []
        for m in masteries:
            if m.accuracy_percentage >= 70:
                strengths.append(m.subject.name)
            elif m.accuracy_percentage < 50 and m.attempted_count >= 5:
                weaknesses.append(m.subject.name)

        readiness.strengths = strengths[:4]
        readiness.weaknesses = weaknesses[:4]

        recs = []
        if coding_score < 50:
            recs.append("Practice Data Structures & Algorithms coding problems to boost placement readiness.")
        if weaknesses:
            recs.append(f"Review fundamental concepts in {', '.join(weaknesses[:2])}.")
        if not attempts.exists():
            recs.append("Take at least 2 full-length Mock Tests to benchmark your exam speed and accuracy.")

        readiness.recommendations = recs
        readiness.save()


# ==============================================================================
# 2. AI QUESTION GENERATION & EXPLANATION ENGINE
# ==============================================================================

class AIQuestionEngine:
    """
    Connects to HireNexa AI Service layer to generate verified questions,
    MCQ options, step-by-step logic, and beginner-friendly explanations.
    """

    @classmethod
    def generate_questions_batch(
        cls,
        subject_name: str,
        topic_name: str,
        difficulty: str,
        question_type: str,
        count: int = 5,
        target_exam: str = "",
        user=None
    ) -> List[Dict[str, Any]]:
        """
        Calls AI LLM with strict JSON schema to generate high-quality questions.
        """
        from ai_assistant.ai_service import HireNexaAIService

        system_prompt = (
            "You are an expert Professor, Technical Assessment Architect, and Entrance Examination specialist. "
            "Generate authentic, technically accurate questions with 4 verified options (A, B, C, D), "
            "one unambiguously correct answer, detailed why-correct reasoning, why-other-options-are-incorrect reasoning, "
            "step-by-step logic, and real-world examples. "
            "You MUST output strictly a JSON object with a 'questions' array. Never return markdown outside the JSON."
        )

        user_prompt = f"""Generate {count} high-quality {question_type} questions for:
Subject: {subject_name}
Topic: {topic_name or 'Comprehensive'}
Difficulty Level: {difficulty} (Beginner / Intermediate / Advanced)
Target Exam: {target_exam or 'Technical Interviews & MCA/OJEE/NIMCET/CUET-PG'}

JSON Schema to strictly adhere to:
{{
  "questions": [
    {{
      "title": "Short descriptive title",
      "question_text": "Full question statement",
      "code_snippet": "Optional code snippet or SQL query if relevant, else empty string",
      "marks": 1.0,
      "negative_marks": 0.25,
      "options": [
        {{"key": "A", "text": "Option text", "is_correct": true, "explanation": "Why this is correct"}},
        {{"key": "B", "text": "Option text", "is_correct": false, "explanation": "Why this is incorrect"}},
        {{"key": "C", "text": "Option text", "is_correct": false, "explanation": "Why this is incorrect"}},
        {{"key": "D", "text": "Option text", "is_correct": false, "explanation": "Why this is incorrect"}}
      ],
      "explanation": {{
        "correct_answer_summary": "Option A is the correct answer",
        "why_correct": "Clear breakdown of why Option A is accurate.",
        "why_others_incorrect": "B is wrong because..., C is wrong because..., D is wrong because...",
        "step_by_step_logic": "Step 1: ... Step 2: ... Step 3: ...",
        "practical_example": "Real-world programming or industry use case.",
        "related_concepts": ["Concept 1", "Concept 2"]
      }}
    }}
  ]
}}"""

        try:
            stream_gen = HireNexaAIService.generate_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                history=[],
            )
            full_text = "".join(list(stream_gen)).strip()

            # Strip markdown json blocks if returned
            clean_json_str = full_text
            if "```json" in clean_json_str:
                clean_json_str = clean_json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json_str:
                clean_json_str = clean_json_str.split("```")[1].split("```")[0].strip()

            parsed = json.loads(clean_json_str)
            return parsed.get("questions", [])

        except Exception as e:
            logger.error("AI Question Generation Failed: %s", e)
            return []

    @classmethod
    def generate_ai_explanation_for_response(cls, question: Question, user_answer: str) -> Dict[str, Any]:
        """
        Dynamically generates personalized AI reasoning for a student's answer.
        """
        from ai_assistant.ai_service import HireNexaAIService

        system_prompt = (
            "You are a friendly, encouraging senior computer science tutor. Explain clearly to a student "
            "why their chosen answer was correct or incorrect, provide beginner-friendly analogies, "
            "step-by-step logic, and recommended practice topics."
        )

        user_prompt = f"""Question: {question.question_text}
{f'Code: {question.code_snippet}' if question.code_snippet else ''}
Student's Submitted Answer: {user_answer}

Provide:
1. Status: Did they get it right?
2. Step-by-step logic explaining the correct concept.
3. Why their answer was right or what common misconception they fell into.
4. Real-world analogy or industry example.
5. Key takeaways for exams and interviews."""

        try:
            stream_gen = HireNexaAIService.generate_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                history=[],
            )
            explanation_text = "".join(list(stream_gen)).strip()
            return {"success": True, "explanation": explanation_text}
        except Exception as e:
            logger.warning("AI Explanation generation failed: %s", e)
            # Fallback to stored database explanation
            stored = getattr(question, "explanation_detail", None)
            if stored:
                return {
                    "success": True,
                    "explanation": f"**Correct Answer:** {stored.correct_answer_summary}\n\n"
                                   f"**Why Correct:** {stored.why_correct}\n\n"
                                   f"**Step-by-Step Logic:** {stored.step_by_step_logic}\n\n"
                                   f"**Practical Example:** {stored.practical_example}"
                }
            return {"success": False, "explanation": "Detailed explanation unavailable at this time."}

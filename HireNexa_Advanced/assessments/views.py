import csv
import io
import json
import logging
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Count, Q, Avg, Sum

logger = logging.getLogger(__name__)
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from accounts.decorators import owner_required
from .models import (
    Stream, Chapter, Subject, Topic, Subtopic, Question, QuestionOption, QuestionExplanation,
    QuestionPackage, Examination, ExamQuestion, ExamAttempt, ExamResponse,
    UserQuestionHistory, TopicCompletion,
    CodingProblem, TestCase, CodingSubmission, StudentSkillMastery,
    PlacementReadiness, CareerOpportunity, AIGenerationBatch,
    EntranceTrack, LearningNote, Result, TopicProgress, SubjectProgress,
    PersonalTarget, AdminReviewHistory
)
from .services import ExamEvaluationService, AIQuestionEngine, QuestionBankShortageError


# ==============================================================================
# 1. DEDICATED MCQ & ENTRANCE EXAM PREPARATION HUB
# ==============================================================================

def mcq_entrance_hub_view(request):
    """
    Main Entrance Examination & MCQ Portal.
    Independent tracks: MCA Entrance (16 Subjects) and MBA Entrance (8 Subjects).
    Subject Cards display:
    - Total Topics
    - Available Learning Notes
    - Total Questions
    - Verified Questions
    - Practice Availability
    - Completion Percentage
    - Learning Progress Percentage
    - Subject Mastery Percentage
    Standardized Topic Tests: exactly 16 questions, 21 minutes, max 5 attempts.
    """
    track_param = request.GET.get("track", "").strip()
    stream_slug = request.GET.get("stream", "").strip()
    subject_slug = request.GET.get("subject", "").strip()
    chapter_slug = request.GET.get("chapter", "").strip()
    exam_filter = request.GET.get("exam", "all").strip().lower()
    difficulty = request.GET.get("difficulty", "").strip().upper()
    pyq_only = request.GET.get("pyq", "").strip() == "1"

    tracks = EntranceTrack.objects.filter(is_active=True).order_by("order")
    
    # Resolve active track (defaults to MCA Entrance if not specified)
    active_track = None
    if track_param:
        active_track = tracks.filter(Q(slug=track_param) | Q(code__iexact=track_param)).first()
    if not active_track and stream_slug:
        active_track = tracks.filter(slug=stream_slug).first()
    if not active_track:
        active_track = tracks.filter(code="MCA").first() or tracks.first()

    # Subjects for the active track
    if active_track:
        subjects_qs = Subject.objects.filter(
            is_active=True, entrance_track=active_track
        ).order_by("order", "name")
    else:
        subjects_qs = Subject.objects.filter(is_active=True).order_by("order", "name")

    # If stream specified without track match, fallback filter
    if stream_slug and not active_track:
        subjects_qs = subjects_qs.filter(stream__slug=stream_slug)

    # Chapters / Topics
    chapters_qs = Chapter.objects.filter(is_active=True).select_related("subject").order_by("order", "name")
    if subject_slug:
        chapters_qs = chapters_qs.filter(subject__slug=subject_slug)

    # Active Tests
    exams_qs = Examination.objects.filter(
        is_published=True, is_active=True
    ).select_related("stream", "entrance_track", "subject", "topic", "chapter").order_by("id")

    if active_track:
        exams_qs = exams_qs.filter(
            Q(entrance_track=active_track) | Q(subject__entrance_track=active_track)
        )
    if subject_slug:
        exams_qs = exams_qs.filter(subject__slug=subject_slug)
    if chapter_slug:
        exams_qs = exams_qs.filter(chapter__slug=chapter_slug)

    if exam_filter in ["nimcet", "ojee", "cuet_pg", "cat", "mat", "cmat", "xat", "snap"]:
        exam_tag_map = {
            "nimcet": "NIMCET",
            "ojee": "OJEE",
            "cuet_pg": "CUET-PG",
            "cat": "CAT",
            "mat": "MAT",
            "cmat": "CMAT",
            "xat": "XAT",
            "snap": "SNAP",
        }
        target_tag = exam_tag_map.get(exam_filter, exam_filter.upper())
        exams_qs = exams_qs.filter(
            Q(target_entrance_exam__icontains=target_tag) |
            Q(title__icontains=target_tag)
        )

    # Live statistics across track and system
    total_mcqs = Question.objects.filter(status=Question.Status.APPROVED).count()
    total_pyqs = Question.objects.filter(is_pyq=True, status=Question.Status.APPROVED).count()
    total_tests = Examination.objects.filter(is_published=True, is_active=True).count()
    total_subjects = subjects_qs.count()

    # User attempts left and topic completion tracking
    user_attempt_counts = {}
    completed_topic_ids = set()
    user_topic_best_scores = {}
    completed_topics_count = 0

    if request.user.is_authenticated:
        counts = ExamAttempt.objects.filter(user=request.user).values("examination_id").annotate(c=Count("id"))
        user_attempt_counts = {item["examination_id"]: item["c"] for item in counts}
        
        comps = TopicCompletion.objects.filter(user=request.user, is_completed=True)
        completed_topic_ids = set(comps.values_list("topic_id", flat=True))
        completed_topics_count = len(completed_topic_ids)
        user_topic_best_scores = {c.topic_id: float(c.best_score or 0) for c in comps}

    # Annotate subjects with rich metrics required by Section 4
    enhanced_subjects = []
    for subj in subjects_qs:
        subj_topics = list(subj.topics.all().order_by("order", "name"))
        t_count = len(subj_topics)
        n_count = LearningNote.objects.filter(subject=subj).count()
        q_count = Question.objects.filter(subject=subj, status=Question.Status.APPROVED).count()
        v_count = Question.objects.filter(subject=subj, status=Question.Status.APPROVED, is_verified=True).count()

        comp_cnt = sum(1 for t in subj_topics if t.id in completed_topic_ids)
        comp_pct = round((comp_cnt / t_count * 100), 1) if t_count > 0 else 0.0

        # Subject mastery calculation: average % score across completed topics
        topic_scores = [user_topic_best_scores[t.id] for t in subj_topics if t.id in user_topic_best_scores]
        if topic_scores:
            mastery_pct = round(sum((sc / 16.0) * 100 for sc in topic_scores) / len(topic_scores), 1)
        else:
            mastery_pct = 0.0

        # Learning progress: ratio of notes accessed / completed topics
        learning_progress = min(100.0, round(comp_pct * 0.9 + (mastery_pct * 0.1), 1))

        # Build topic metadata list with attempt counters
        topics_meta = []
        for top in subj_topics:
            top_exam = Examination.objects.filter(topic=top, is_published=True).first()
            used_att = user_attempt_counts.get(top_exam.id, 0) if top_exam else 0
            left_att = max(0, (top_exam.max_attempts or 5) - used_att) if top_exam else 5
            is_comp = top.id in completed_topic_ids
            best_sc = user_topic_best_scores.get(top.id, None)

            topics_meta.append({
                "id": top.id,
                "name": top.name,
                "slug": top.slug,
                "exam": top_exam,
                "exam_slug": top_exam.slug if top_exam else "",
                "used_attempts": used_att,
                "attempts_left": left_att,
                "is_completed": is_comp,
                "best_score": best_sc,
                "best_score_pct": round((best_sc / 16.0) * 100, 1) if best_sc is not None else None,
                "has_notes": LearningNote.objects.filter(topic=top).exists(),
            })

        enhanced_subjects.append({
            "obj": subj,
            "id": subj.id,
            "name": subj.name,
            "slug": subj.slug,
            "icon": subj.icon,
            "description": subj.description,
            "total_topics": t_count,
            "available_notes": n_count,
            "total_questions": q_count,
            "verified_questions": v_count,
            "practice_available": v_count >= 16,
            "completed_topics_count": comp_cnt,
            "completion_percentage": comp_pct,
            "learning_progress_percentage": learning_progress,
            "subject_mastery_percentage": mastery_pct,
            "topics_list": topics_meta,
        })

    # Attach computed attempts left, completion, and lock attributes to each exam
    exams_list = list(exams_qs)
    for ex in exams_list:
        used = user_attempt_counts.get(ex.id, 0)
        ex.user_attempts_count = used
        ex.user_attempts_left = max(0, (ex.max_attempts or 5) - used)

        if ex.topic_id:
            ex.is_topic_completed = ex.topic_id in completed_topic_ids
        else:
            ex.is_topic_completed = False

        if ex.is_final_combined:
            req = ex.required_topics_count or 1
            if ex.subject_id:
                subj_completed = TopicCompletion.objects.filter(
                    user=request.user, topic__subject_id=ex.subject_id, is_completed=True
                ).count() if request.user.is_authenticated else 0
                ex.is_locked = bool(subj_completed < req)
                ex.completed_topics_count = subj_completed
            else:
                ex.is_locked = bool(completed_topics_count < req)
                ex.completed_topics_count = completed_topics_count
        else:
            ex.is_locked = False

    paginator = Paginator(exams_list, 12)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # Filtered practice questions when an exam or topic is targeted
    featured_questions_qs = Question.objects.filter(status=Question.Status.APPROVED)
    if exam_filter in ["nimcet", "ojee", "cuet_pg", "cat", "mat", "cmat", "xat", "snap"]:
        exam_tag_map = {
            "nimcet": "NIMCET",
            "ojee": "OJEE",
            "cuet_pg": "CUET-PG",
            "cat": "CAT",
            "mat": "MAT",
            "cmat": "CMAT",
            "xat": "XAT",
            "snap": "SNAP",
        }
        target_tag = exam_tag_map.get(exam_filter, exam_filter.upper())
        featured_questions_qs = featured_questions_qs.filter(
            Q(exam__target_entrance_exam__icontains=target_tag) |
            Q(exam__title__icontains=target_tag) |
            Q(exam_instances__examination__target_entrance_exam__icontains=target_tag) |
            Q(pyq_exam__icontains=target_tag)
        ).distinct()
    elif subject_slug:
        featured_questions_qs = featured_questions_qs.filter(subject__slug=subject_slug)
    elif active_track:
        featured_questions_qs = featured_questions_qs.filter(
            Q(subject__entrance_track=active_track) | Q(exam__entrance_track=active_track)
        ).distinct()

    featured_questions = list(featured_questions_qs.select_related("subject", "topic")[:16])

    # Recent previous year questions
    verified_pyqs = Question.objects.filter(
        is_pyq=True, status=Question.Status.APPROVED
    ).select_related("subject").order_by("-pyq_year", "-id")[:8]

    context = {
        "tracks": tracks,
        "active_track": active_track,
        "active_track_slug": active_track.slug if active_track else "",
        "active_track_code": active_track.code if active_track else "",
        "subjects": subjects_qs[:30],
        "enhanced_subjects": enhanced_subjects,
        "chapters": chapters_qs[:40],
        "exams_page": page_obj,
        "mock_tests": page_obj,
        "featured_questions": featured_questions,
        "verified_pyqs": verified_pyqs,
        "active_stream": stream_slug,
        "active_subject": subject_slug,
        "active_chapter": chapter_slug,
        "active_exam_filter": exam_filter,
        "active_difficulty": difficulty,
        "pyq_only": pyq_only,
        "total_pyqs": total_pyqs,
        "total_mcqs": total_mcqs,
        "total_tests": total_tests,
        "total_subjects": total_subjects,
        "completed_topics_count": completed_topics_count,
    }
    return render(request, "assessments/mcq_entrance_hub.html", context)


# ==============================================================================
# 2. COMPREHENSIVE QUESTION BANK & PRACTICE
# ==============================================================================

def question_bank_view(request):
    """
    Searchable, filterable question repository across all 21 subjects,
    5 difficulty levels, and 12 question formats.
    """
    subject_slug = request.GET.get("subject", "").strip()
    topic_slug = request.GET.get("topic", "").strip()
    difficulty = request.GET.get("difficulty", "").strip().upper()
    q_type = request.GET.get("type", "").strip().upper()
    search_query = request.GET.get("q", "").strip()

    subjects = Subject.objects.filter(is_active=True).order_by("order", "name")
    questions_qs = Question.objects.filter(
        status=Question.Status.APPROVED
    ).select_related("subject", "topic").prefetch_related("options")

    if subject_slug:
        questions_qs = questions_qs.filter(subject__slug=subject_slug)
    if topic_slug:
        questions_qs = questions_qs.filter(topic__slug=topic_slug)
    if difficulty:
        questions_qs = questions_qs.filter(difficulty=difficulty)
    if q_type:
        questions_qs = questions_qs.filter(question_type=q_type)
    if search_query:
        questions_qs = questions_qs.filter(
            Q(title__icontains=search_query) |
            Q(question_text__icontains=search_query) |
            Q(tags__icontains=search_query)
        )

    paginator = Paginator(questions_qs, 15)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "subjects": subjects,
        "questions": page_obj,
        "selected_subject": subject_slug,
        "selected_difficulty": difficulty,
        "selected_type": q_type,
        "search_query": search_query,
        "difficulty_levels": Question.Level.choices,
        "question_types": Question.Type.choices,
    }
    return render(request, "assessments/question_bank.html", context)


def question_detail_view(request, question_id):
    """
    Interactive single question solve, instant option verification,
    and step-by-step logic breakdown.
    """
    question = get_object_or_404(
        Question.objects.select_related("subject", "topic").prefetch_related("options"),
        id=question_id,
        status=Question.Status.APPROVED
    )
    explanation = getattr(question, "explanation_detail", None)

    # Related practice questions
    related_qs = Question.objects.filter(
        subject=question.subject,
        status=Question.Status.APPROVED
    ).exclude(id=question.id)[:4]

    context = {
        "question": question,
        "options": question.options.all().order_by("order", "option_key"),
        "explanation": explanation,
        "related_questions": related_qs,
    }
    return render(request, "assessments/question_detail.html", context)


# ==============================================================================
# 3. LIVE EXAMINATION SYSTEM
# ==============================================================================

def exam_list_view(request):
    """
    Directory of live exams, entrance mock tests, and daily/weekly drills.
    """
    category = request.GET.get("category", "").strip().upper()
    exams_qs = Examination.objects.filter(is_published=True, is_active=True).select_related("subject", "stream", "chapter").order_by("-id")

    if category:
        exams_qs = exams_qs.filter(category=category)

    user_attempts = {}
    user_attempt_counts = {}
    if request.user.is_authenticated:
        attempts = ExamAttempt.objects.filter(user=request.user)
        for att in attempts:
            user_attempts[att.examination_id] = att
            user_attempt_counts[att.examination_id] = user_attempt_counts.get(att.examination_id, 0) + 1

    exams_list = list(exams_qs)
    for ex in exams_list:
        used = user_attempt_counts.get(ex.id, 0)
        ex.user_attempts_count = used
        ex.user_attempts_left = max(0, (ex.max_attempts or 5) - used)

    context = {
        "exams": exams_list,
        "categories": Examination.Category.choices,
        "selected_category": category,
        "user_attempts": user_attempts,
    }
    return render(request, "assessments/exam_list.html", context)


@login_required
def exam_start_view(request, exam_slug):
    """
    Pre-exam instructions and launcher.
    Enforces maximum 5 attempts per candidate per test on the server.
    Catches question-bank shortage and displays clear educational notice.
    """
    examination = get_object_or_404(
        Examination.objects.select_related("entrance_track", "subject", "topic"),
        slug=exam_slug,
        is_published=True
    )

    user_attempts = ExamAttempt.objects.filter(
        user=request.user,
        examination=examination
    ).order_by("attempt_number")

    attempts_count = user_attempts.count()
    max_attempts = examination.max_attempts or 5
    attempts_left = max(0, max_attempts - attempts_count)

    active_attempt = user_attempts.filter(status=ExamAttempt.Status.IN_PROGRESS).first()
    if active_attempt and active_attempt.is_expired:
        ExamEvaluationService.finalize_submission(active_attempt, auto_timed_out=True)
        active_attempt = None
        attempts_count = ExamAttempt.objects.filter(user=request.user, examination=examination).count()
        attempts_left = max(0, max_attempts - attempts_count)

    # Check if final combined exam is locked
    is_locked = False
    completed_topics_count = 0
    if examination.is_final_combined:
        top_filter = Q(user=request.user, is_completed=True)
        if examination.subject:
            top_filter &= Q(topic__subject=examination.subject)
        completed_topics_count = TopicCompletion.objects.filter(top_filter).count()
        req = examination.required_topics_count or 1
        if completed_topics_count < req:
            is_locked = True

    if request.method == "POST":
        if is_locked:
            messages.warning(
                request,
                f"This Final Combined Examination is locked. You must complete all {examination.required_topics_count} "
                f"required topics before unlocking this examination. (Completed: {completed_topics_count}/{examination.required_topics_count})"
            )
            return redirect("mcq_entrance_hub")
        if attempts_left <= 0 and not active_attempt:
            messages.error(request, f"You have reached the maximum allowed limit of {max_attempts} attempts for this examination.")
            return redirect("exam_start", exam_slug=exam_slug)
        try:
            attempt, created = ExamEvaluationService.start_or_resume_attempt(request.user, examination)
            if not created:
                messages.info(request, "Your examination attempt is already active. Resuming your examination.")
            return redirect("exam_live", attempt_id=attempt.id)
        except QuestionBankShortageError as e:
            messages.error(
                request,
                f"Question Bank Shortage: Only {e.available} verified questions are currently available for '{e.topic_name}' "
                f"(requires {e.required}). To protect standardized examination integrity, incomplete tests are not generated. "
                f"Please review the Topic Learning Notes while the question bank is updated."
            )
            return redirect("exam_start", exam_slug=exam_slug)
        except PermissionError as e:
            messages.error(request, str(e))
            return redirect("exam_start", exam_slug=exam_slug)
        except IntegrityError:
            active = ExamAttempt.objects.filter(
                user=request.user, examination=examination, status=ExamAttempt.Status.IN_PROGRESS
            ).first()
            if active:
                messages.info(request, "Your examination attempt is already active. Resuming your examination.")
                return redirect("exam_live", attempt_id=active.id)
            latest = ExamAttempt.objects.filter(
                user=request.user, examination=examination
            ).order_by("-attempt_number").first()
            if latest and latest.status in [ExamAttempt.Status.SUBMITTED, ExamAttempt.Status.EXPIRED, ExamAttempt.Status.TIMED_OUT]:
                messages.info(request, "Your previous examination has been submitted.")
                return redirect("exam_result", attempt_id=latest.id)
            messages.error(request, "Unable to start the examination at this moment. Please try again.")
            return redirect("exam_start", exam_slug=exam_slug)
        except Exception:
            logger.exception("Unexpected error starting examination for user %s, exam %s", request.user.id, exam_slug)
            messages.error(request, "Unable to start the examination. Please try again.")
            return redirect("exam_start", exam_slug=exam_slug)

    context = {
        "exam": examination,
        "active_attempt": active_attempt,
        "questions_count": examination.questions_count or 16,
        "duration_minutes": examination.duration_minutes or 21,
        "attempts_count": attempts_count,
        "max_attempts": max_attempts,
        "attempts_left": attempts_left,
        "user_attempts": user_attempts,
        "is_locked": is_locked,
        "completed_topics_count": completed_topics_count,
    }
    return render(request, "assessments/exam_instructions.html", context)


@login_required
def exam_live_view(request, attempt_id):
    """
    Professional CBT-Style Live Examination Interface:
    - Real-time countdown timer synchronized with server expiration (never restarts on refresh).
    - Question Palette displaying 4 discrete question states:
        1. Answered (Green)
        2. Unanswered (Gray/White)
        3. Marked for Review (Purple/Blue)
        4. Answered and Marked for Review (Purple with Green badge)
    - Autosave with state preservation.
    - Shuffled options frozen in AttemptQuestion snapshots.
    - Pre-submission summary modal with confirmation.
    """
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("examination", "examination__subject", "examination__topic"),
        id=attempt_id,
        user=request.user
    )

    if attempt.status != ExamAttempt.Status.IN_PROGRESS:
        return redirect("exam_result", attempt_id=attempt.id)

    # Check if expired
    if attempt.is_expired:
        ExamEvaluationService.finalize_submission(attempt, auto_timed_out=True)
        return redirect("exam_result", attempt_id=attempt.id)

    # Fetch ordered questions from frozen snapshots or IDs
    attempt_qs = list(attempt.attempt_questions.select_related("question").prefetch_related("question__options").order_by("question_order"))
    ordered_questions = []

    if attempt_qs:
        for aq in attempt_qs:
            q = aq.question
            all_opts = {opt.id: opt for opt in q.options.all()}
            if aq.shuffled_option_ids:
                shuffled = [all_opts[oid] for oid in aq.shuffled_option_ids if oid in all_opts]
                remaining = [opt for opt in all_opts.values() if opt.id not in set(aq.shuffled_option_ids)]
                q.shuffled_options = shuffled + remaining
            else:
                q.shuffled_options = list(q.options.all().order_by("order", "id"))
            ordered_questions.append(q)
    else:
        q_ids = attempt.ordered_question_ids or list(
            attempt.examination.questions.filter(status=Question.Status.APPROVED).order_by("order", "id").values_list("id", flat=True)
        )
        questions_qs = Question.objects.filter(id__in=q_ids).prefetch_related("options")
        questions_dict = {q.id: q for q in questions_qs}
        ordered_questions = [questions_dict[qid] for qid in q_ids if qid in questions_dict]
        import random
        for q in ordered_questions:
            options = list(q.options.all().order_by("order", "id"))
            if attempt.examination.shuffle_options and attempt.random_seed:
                opt_rng = random.Random(f"{attempt.random_seed}-{q.id}")
                opt_rng.shuffle(options)
            q.shuffled_options = options

    # Existing candidate responses map
    responses = {r.question_id: r for r in attempt.responses.all()}

    # Prepare palette data and client-side rehydration state for 4 question states
    palette = []
    saved_state = {}
    cnt_answered = 0
    cnt_unanswered = 0
    cnt_marked_review = 0
    cnt_answered_review = 0

    for idx, q in enumerate(ordered_questions, start=1):
        resp = responses.get(q.id)
        has_ans = bool(resp and (resp.selected_option_ids or resp.text_answer))
        is_review = bool(resp and resp.is_marked_for_review)
        sel_opt = resp.selected_option_ids[0] if (resp and resp.selected_option_ids) else None

        q.user_selected_option_ids = resp.selected_option_ids if resp else []
        saved_state[idx] = {
            "answered": has_ans,
            "review": is_review,
            "selectedOption": sel_opt,
        }

        # Determine 4 separate question states
        if has_ans and is_review:
            status_class = "answered-review"
            cnt_answered_review += 1
        elif is_review:
            status_class = "marked-review"
            cnt_marked_review += 1
        elif has_ans:
            status_class = "answered"
            cnt_answered += 1
        else:
            status_class = "unanswered"
            cnt_unanswered += 1

        palette.append({
            "index": idx,
            "question_id": q.id,
            "status_class": status_class,
        })

    context = {
        "attempt": attempt,
        "exam": attempt.examination,
        "questions": ordered_questions,
        "responses": responses,
        "palette": palette,
        "saved_state_json": json.dumps(saved_state),
        "seconds_remaining": attempt.seconds_remaining,
        "total_questions": len(ordered_questions),
        "cnt_answered": cnt_answered,
        "cnt_unanswered": cnt_unanswered,
        "cnt_marked_review": cnt_marked_review,
        "cnt_answered_review": cnt_answered_review,
    }
    return render(request, "assessments/exam_live.html", context)


@login_required
def exam_result_view(request, attempt_id):
    """
    Ultra-Advanced Examination Result and Percentage Analytics:
    - Positive Marks (+1.00 each)
    - Negative Marks (-0.25 each)
    - Final Score & Maximum Possible Score
    - Score Percentage, Accuracy Percentage, Completion Percentage, Time Utilization Percentage
    - Attempt History & Score Progression (Attempts 1-5 with delta changes)
    - Personal Target Comparison & Gap Analysis
    - Verified Question-by-Question Pedagogical Review
    """
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("examination", "examination__subject", "examination__topic"),
        id=attempt_id,
        user=request.user
    )

    # Ensure submission is finalized
    if attempt.status == ExamAttempt.Status.IN_PROGRESS:
        ExamEvaluationService.finalize_submission(attempt, auto_timed_out=False)
        attempt.refresh_from_db()

    # Load Result model entity
    result = Result.objects.filter(attempt=attempt).first()
    if not result:
        # Generate result if missing
        ExamEvaluationService.finalize_submission(attempt, auto_timed_out=False, force_recalculate=True)
        attempt.refresh_from_db()
        result = Result.objects.filter(attempt=attempt).first()

    responses_qs = attempt.responses.select_related(
        "question", "question__chapter", "question__topic", "question__explanation_detail"
    ).prefetch_related("question__options").all()

    # Reorder according to attempt's question ordering
    q_order = {qid: idx for idx, qid in enumerate(attempt.ordered_question_ids or [])}
    responses = sorted(responses_qs, key=lambda r: q_order.get(r.question_id, 0))

    # All attempts table for this user & exam (Attempts 1 to 5)
    all_attempts = list(ExamAttempt.objects.filter(
        user=request.user,
        examination=attempt.examination,
        status__in=[ExamAttempt.Status.SUBMITTED, ExamAttempt.Status.EXPIRED]
    ).order_by("attempt_number"))

    attempts_history = []
    prev_score = None
    for att in all_attempts:
        att_res = Result.objects.filter(attempt=att).first()
        delta = None
        if prev_score is not None:
            delta = round(float(att.score) - prev_score, 2)
        prev_score = float(att.score)

        attempts_history.append({
            "attempt_number": att.attempt_number,
            "date": att.submitted_at.strftime("%b %d, %Y %H:%M") if att.submitted_at else "—",
            "score": float(att.score),
            "percentage": float(att.percentage),
            "accuracy": float(att_res.accuracy_percentage) if att_res else 0.0,
            "completion": float(att_res.completion_percentage) if att_res else 0.0,
            "time_used": int((att.submitted_at - att.started_at).total_seconds()) if (att.submitted_at and att.started_at) else 0,
            "delta": delta,
            "is_current": att.id == attempt.id,
        })

    best_score = max((a.score for a in all_attempts), default=attempt.score)
    avg_score = round(sum((float(a.score) for a in all_attempts), 0.0) / len(all_attempts), 2) if all_attempts else float(attempt.score)
    max_attempts = attempt.examination.max_attempts or 5
    attempts_left = max(0, max_attempts - len(all_attempts))

    # Personal Target comparison
    user_target = PersonalTarget.objects.filter(user=request.user).first()
    target_pct = float(user_target.target_percentage) if user_target else 75.0
    current_score_pct = float(result.score_percentage if result else attempt.percentage)
    target_gap = round(current_score_pct - target_pct, 2)

    # Per-topic accuracy breakdown
    topic_breakdown = {}
    for resp in responses:
        q = resp.question
        top_name = (q.chapter.name if q.chapter else (q.topic.name if q.topic else "General"))
        if top_name not in topic_breakdown:
            topic_breakdown[top_name] = {"total": 0, "correct": 0, "incorrect": 0, "skipped": 0}
        topic_breakdown[top_name]["total"] += 1
        if resp.is_correct is True:
            topic_breakdown[top_name]["correct"] += 1
        elif resp.is_correct is False:
            topic_breakdown[top_name]["incorrect"] += 1
        else:
            topic_breakdown[top_name]["skipped"] += 1

    for t_data in topic_breakdown.values():
        t_data["accuracy"] = round((t_data["correct"] / t_data["total"]) * 100, 1) if t_data["total"] > 0 else 0.0

    context = {
        "attempt": attempt,
        "exam": attempt.examination,
        "result": result,
        "responses": responses,
        "all_attempts": all_attempts,
        "attempts_history": attempts_history,
        "best_score": best_score,
        "avg_score": avg_score,
        "latest_score": all_attempts[-1].score if all_attempts else attempt.score,
        "max_attempts": max_attempts,
        "attempts_left": attempts_left,
        "target_pct": target_pct,
        "target_gap": target_gap,
        "topic_breakdown": topic_breakdown,
        "time_taken_seconds": int((attempt.submitted_at - attempt.started_at).total_seconds()) if attempt.submitted_at else 0,
    }
    return render(request, "assessments/exam_result.html", context)


@login_required
def practice_wrong_questions_view(request, attempt_id):
    """
    Dedicated practice session displaying incorrect or skipped questions from
    a submitted attempt so students can master their weak areas without modifying
    their original exam attempt score.
    """
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("examination", "examination__subject"),
        id=attempt_id,
        user=request.user
    )

    responses_qs = attempt.responses.filter(
        Q(is_correct=False) | Q(is_correct__isnull=True)
    ).select_related("question", "question__subject", "question__topic", "question__explanation_detail").prefetch_related("question__options")

    wrong_responses = list(responses_qs)

    context = {
        "attempt": attempt,
        "exam": attempt.examination,
        "responses": wrong_responses,
        "wrong_count": len(wrong_responses),
        "total_count": attempt.total_questions,
    }
    return render(request, "assessments/practice_wrong_questions.html", context)


# ==============================================================================
# 4. HACKERRANK-STYLE CODING PRACTICE
# ==============================================================================

def coding_list_view(request):
    """
    List of coding challenges with difficulty, language tags, and solved badges.
    """
    difficulty = request.GET.get("difficulty", "").strip().upper()
    search = request.GET.get("q", "").strip()

    problems_qs = CodingProblem.objects.select_related("subject").annotate(
        test_cases_count=Count("test_cases")
    ).order_by("difficulty", "title")

    if difficulty in ["EASY", "MEDIUM", "HARD", "EXPERT"]:
        problems_qs = problems_qs.filter(difficulty=difficulty)
    if search:
        problems_qs = problems_qs.filter(
            Q(title__icontains=search) | Q(tags__icontains=search)
        )

    user_solved_ids = set()
    if request.user.is_authenticated:
        user_solved_ids = set(
            CodingSubmission.objects.filter(
                user=request.user,
                status=CodingSubmission.Status.ACCEPTED
            ).values_list("problem_id", flat=True)
        )

    context = {
        "problems": problems_qs,
        "user_solved_ids": user_solved_ids,
        "selected_difficulty": difficulty,
        "search_query": search,
    }
    return render(request, "assessments/coding_list.html", context)


def coding_workspace_view(request, problem_slug):
    """
    HackerRank-style code editor IDE with multi-language run/submit,
    sample test case verification, custom inputs, and submission history.
    """
    problem = get_object_or_404(
        CodingProblem.objects.prefetch_related("test_cases"),
        slug=problem_slug
    )
    sample_cases = problem.test_cases.filter(is_hidden=False)

    user_submissions = []
    if request.user.is_authenticated:
        user_submissions = CodingSubmission.objects.filter(
            user=request.user,
            problem=problem
        ).order_by("-submitted_at")[:10]

    context = {
        "problem": problem,
        "sample_cases": sample_cases,
        "user_submissions": user_submissions,
        "starter_templates_json": json.dumps(problem.starter_templates or {}),
        "allowed_languages": problem.allowed_languages or ["python", "javascript", "c", "cpp", "java"],
    }
    return render(request, "assessments/coding_workspace.html", context)


# ==============================================================================
# 5. SPECIAL INTERVIEW TOPICS PACKAGES
# ==============================================================================

def special_interview_hub_view(request):
    """
    Curated interview learning packages (Why React was introduced,
    Why Angular was introduced, React vs Angular, FDE, AI Monitoring, etc.).
    """
    packages = QuestionPackage.objects.filter(
        category=QuestionPackage.Category.SPECIAL_INTERVIEW,
        is_featured=True
    ).prefetch_related("questions")

    context = {
        "packages": packages,
    }
    return render(request, "assessments/special_interview_hub.html", context)


def special_interview_detail_view(request, package_slug):
    """
    Deep-dive module for a special interview topic package.
    """
    package = get_object_or_404(QuestionPackage, slug=package_slug)
    questions = package.questions.filter(
        status=Question.Status.APPROVED
    ).prefetch_related("options", "explanation_detail")

    context = {
        "package": package,
        "questions": questions,
    }
    return render(request, "assessments/special_interview_detail.html", context)


# ==============================================================================
# 6. STUDENT DASHBOARD & CAREER PREPARATION
# ==============================================================================

@login_required
def student_dashboard_view(request):
    """
    Student assessment analytics, skill radar, weak topics, and placement readiness.
    """
    user = request.user
    ExamEvaluationService.recalculate_placement_readiness(user)

    readiness, _ = PlacementReadiness.objects.get_or_create(user=user)
    skill_masteries = StudentSkillMastery.objects.filter(user=user).select_related("subject")

    recent_attempts = ExamAttempt.objects.filter(
        user=user,
        status__in=[ExamAttempt.Status.SUBMITTED, ExamAttempt.Status.TIMED_OUT]
    ).select_related("examination").order_by("-submitted_at")[:5]

    total_attempts = ExamAttempt.objects.filter(user=user).count()
    coding_solved = CodingSubmission.objects.filter(
        user=user,
        status=CodingSubmission.Status.ACCEPTED
    ).values("problem_id").distinct().count()

    total_q_solved = ExamResponse.objects.filter(
        attempt__user=user,
        is_correct=True
    ).count()

    avg_score = ExamAttempt.objects.filter(
        user=user,
        status__in=[ExamAttempt.Status.SUBMITTED, ExamAttempt.Status.TIMED_OUT]
    ).aggregate(Avg("percentage"))["percentage__avg"] or 0.0

    context = {
        "readiness": readiness,
        "skill_masteries": skill_masteries,
        "recent_attempts": recent_attempts,
        "total_attempts": total_attempts,
        "coding_solved": coding_solved,
        "total_q_solved": total_q_solved,
        "avg_score": round(avg_score, 1),
    }
    return render(request, "assessments/student_dashboard.html", context)


def career_prep_view(request):
    """
    Career & Placement Preparation Dashboard:
    - Verified internship & training opportunities (with verified sources).
    - Company-specific pattern guides (TCS, Infosys, Wipro, Google, Amazon).
    - HR & Technical interview preparation.
    """
    opportunities = CareerOpportunity.objects.filter(is_active=True).order_by("-verification_date")

    # Read student readiness if logged in
    readiness = None
    if request.user.is_authenticated:
        readiness = PlacementReadiness.objects.filter(user=request.user).first()

    context = {
        "opportunities": opportunities,
        "readiness": readiness,
    }
    return render(request, "assessments/career_preparation.html", context)


# ==============================================================================
# 7. ADMIN ASSESSMENT SUITE (ROLE-BASED GOVERNANCE)
# ==============================================================================

@owner_required
def admin_assessment_hub_view(request):
    """
    Management suite for platform owners to administer questions,
    bulk CSV/JSON imports, AI generation queues, and mock tests.
    """
    subjects = Subject.objects.all().order_by("name")
    pending_ai_questions = Question.objects.filter(
        status=Question.Status.AI_GENERATED
    ).select_related("subject", "topic").order_by("-created_at")[:20]

    all_exams = Examination.objects.all().order_by("-created_at")[:15]
    recent_submissions = CodingSubmission.objects.select_related(
        "user", "problem"
    ).order_by("-submitted_at")[:15]

    total_questions = Question.objects.count()
    approved_questions = Question.objects.filter(status=Question.Status.APPROVED).count()
    total_exams = Examination.objects.count()
    total_submissions = CodingSubmission.objects.count()

    topic_stats = Topic.objects.annotate(
        approved_count=Count("questions", filter=Q(questions__status=Question.Status.APPROVED))
    ).select_related("subject").order_by("subject__name", "order")[:40]

    duplicate_titles_count = Question.objects.values("title").annotate(
        c=Count("id")
    ).filter(c__gt=1).count()

    context = {
        "subjects": subjects,
        "pending_ai_questions": pending_ai_questions,
        "all_exams": all_exams,
        "recent_submissions": recent_submissions,
        "total_questions": total_questions,
        "approved_questions": approved_questions,
        "total_exams": total_exams,
        "total_submissions": total_submissions,
        "topic_stats": topic_stats,
        "duplicate_titles_count": duplicate_titles_count,
    }
    return render(request, "assessments/admin_assessment_hub.html", context)


@owner_required
def admin_question_action_view(request, question_id, action):
    """
    Approve, Reject, or Delete an AI-generated or draft question.
    """
    question = get_object_or_404(Question, id=question_id)
    if action == "approve":
        question.status = Question.Status.APPROVED
        question.approved_by = request.user
        question.save(update_fields=["status", "approved_by"])
        messages.success(request, f"Question #{question.id} '{question.title}' approved and published.")
    elif action == "reject":
        question.status = Question.Status.REJECTED
        question.save(update_fields=["status"])
        messages.warning(request, f"Question #{question.id} rejected.")
    elif action == "delete":
        question.delete()
        messages.info(request, "Question deleted.")

    return redirect("admin_assessment_hub")


@owner_required
def admin_bulk_import_questions_view(request):
    """
    Bulk import questions from CSV or JSON file format.
    """
    if request.method == "POST" and request.FILES.get("question_file"):
        upload = request.FILES["question_file"]
        filename = upload.name.lower()
        success_cnt = 0

        try:
            if filename.endswith(".json"):
                data = json.load(upload)
                items = data if isinstance(data, list) else data.get("questions", [])
                for item in items:
                    s_name = item.get("subject", "General CS").strip()
                    subj = Subject.objects.filter(name=s_name).first()
                    if not subj:
                        subj = Subject.objects.create(name=s_name, slug=slugify(s_name))
                    q = Question.objects.create(
                        subject=subj,
                        title=item.get("title", "Imported Question"),
                        question_text=item.get("question_text", ""),
                        difficulty=item.get("difficulty", "BEGINNER"),
                        question_type=item.get("type", "MCQ"),
                        marks=Decimal(str(item.get("marks", 1.0))),
                        status=Question.Status.APPROVED,
                        created_by=request.user,
                    )
                    for opt in item.get("options", []):
                        QuestionOption.objects.create(
                            question=q,
                            option_key=opt.get("key", "A"),
                            option_text=opt.get("text", ""),
                            is_correct=bool(opt.get("is_correct", False)),
                        )
                    success_cnt += 1

            elif filename.endswith(".csv"):
                decoded_file = upload.read().decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(decoded_file))
                for row in reader:
                    s_name = row.get("subject", "General CS").strip()
                    subj = Subject.objects.filter(name=s_name).first()
                    if not subj:
                        subj = Subject.objects.create(name=s_name, slug=slugify(s_name))
                    q = Question.objects.create(
                        subject=subj,
                        title=row.get("title", "Imported Question").strip(),
                        question_text=row.get("question_text", "").strip(),
                        difficulty=row.get("difficulty", "BEGINNER").strip().upper(),
                        question_type="MCQ",
                        marks=Decimal(str(row.get("marks", 1.0))),
                        status=Question.Status.APPROVED,
                        created_by=request.user,
                    )
                    # Options A, B, C, D
                    correct_key = row.get("correct_option", "A").strip().upper()
                    for key in ["A", "B", "C", "D"]:
                        opt_val = row.get(f"option_{key.lower()}", "").strip()
                        if opt_val:
                            QuestionOption.objects.create(
                                question=q,
                                option_key=key,
                                option_text=opt_val,
                                is_correct=(key == correct_key),
                            )
                    success_cnt += 1

            messages.success(request, f"Successfully imported {success_cnt} verified questions.")
        except Exception as e:
            messages.error(request, f"Import failed: {str(e)}")

    return redirect("admin_assessment_hub")


# ==============================================================================
# 5. TOPIC LEARNING NOTES & EDUCATIONAL SYSTEM (SECTION 7)
# ==============================================================================

def topic_learning_notes_view(request, topic_id):
    """
    Renders comprehensive educational material for a topic:
    - Concept Understanding (Summary, Definition, Principles, Applications, Pros/Cons, Pitfalls)
    - Step-by-Step Examples (Beginner, Intermediate, Advanced)
    - Visual Comparison Tables
    - Quick Revision Formulas & Exam High-Yield Points
    - Curated Practice Problems with Revealed Step-by-Step Logic
    """
    topic = get_object_or_404(Topic.objects.select_related("subject", "subject__entrance_track"), id=topic_id)
    subject = topic.subject
    
    note = getattr(topic, "learning_note", None)
    if not note:
        note = LearningNote.objects.filter(topic=topic).first()

    # If missing, generate dynamic fallback
    from .question_engine import generate_learning_notes_for_topic
    if not note:
        note_data = generate_learning_notes_for_topic(subject.name, topic.name)
        note = LearningNote.objects.create(
            topic=topic,
            subject=subject,
            concept_summary=note_data["concept_summary"],
            detailed_explanation=note_data["detailed_explanation"],
            real_world_applications=note_data["real_world_applications"],
            advantages_disadvantages=note_data["advantages_disadvantages"],
            comparison_table_markdown=note_data["comparison_table_markdown"],
            common_pitfalls=note_data["common_pitfalls"],
            examples_json=note_data["examples_json"],
            quick_revision_formulas=note_data["quick_revision_formulas"],
            practice_questions_json=note_data["practice_questions_json"],
        )

    # Associated Examination for this topic
    exam = Examination.objects.filter(topic=topic, is_published=True).first()
    
    # User's attempts on this topic
    attempts_used = 0
    attempts_left = 5
    best_score = None
    if request.user.is_authenticated and exam:
        past_attempts = ExamAttempt.objects.filter(user=request.user, examination=exam)
        attempts_used = past_attempts.count()
        attempts_left = max(0, (exam.max_attempts or 5) - attempts_used)
        if attempts_used > 0:
            best_score = max((a.score for a in past_attempts), default=0)

    # Related topics in same subject
    related_topics = Topic.objects.filter(subject=subject).exclude(id=topic.id).order_by("order")[:6]

    context = {
        "topic": topic,
        "subject": subject,
        "note": note,
        "exam": exam,
        "attempts_used": attempts_used,
        "attempts_left": attempts_left,
        "best_score": best_score,
        "related_topics": related_topics,
    }
    return render(request, "assessments/learning_notes.html", context)


# ==============================================================================
# 6. PERFORMANCE ANALYTICS & TARGET GAP ENGINE (SECTIONS 9, 11, 14)
# ==============================================================================

@login_required
def performance_analytics_dashboard_view(request):
    """
    Candidate Performance Analytics Dashboard:
    - Overall Entrance Track score %, accuracy %, completion %
    - Subject Mastery Breakdown across MCA & MBA tracks
    - Attempt progression & score stability trends (Attempts 1-5)
    - Personal Target vs Actual Gap Analysis
    - Persistent Weak Topics (< 60% accuracy)
    """
    user = request.user
    results = Result.objects.filter(user=user).select_related("examination", "examination__subject")
    
    total_tests_taken = results.count()
    if total_tests_taken > 0:
        avg_score_pct = round(results.aggregate(a=Avg("score_percentage"))["a"] or 0.0, 2)
        avg_accuracy_pct = round(results.aggregate(a=Avg("accuracy_percentage"))["a"] or 0.0, 2)
        avg_completion_pct = round(results.aggregate(a=Avg("completion_percentage"))["a"] or 0.0, 2)
        total_qs_solved = results.aggregate(s=Sum("correct_answers"))["s"] or 0
    else:
        avg_score_pct = 0.0
        avg_accuracy_pct = 0.0
        avg_completion_pct = 0.0
        total_qs_solved = 0

    # Subject Mastery Aggregation
    subjects = Subject.objects.filter(is_active=True).select_related("entrance_track").order_by("order")
    subject_analytics = []
    
    for subj in subjects:
        subj_results = results.filter(examination__subject=subj)
        count = subj_results.count()
        if count > 0:
            s_score = round(subj_results.aggregate(a=Avg("score_percentage"))["a"] or 0.0, 1)
            s_acc = round(subj_results.aggregate(a=Avg("accuracy_percentage"))["a"] or 0.0, 1)
        else:
            s_score = 0.0
            s_acc = 0.0

        subject_analytics.append({
            "subject": subj,
            "track": subj.entrance_track.name if subj.entrance_track else "General",
            "tests_taken": count,
            "mastery_score_pct": s_score,
            "accuracy_pct": s_acc,
        })

    # Weak Topics Identification (< 60% accuracy)
    weak_topics = []
    topic_comps = TopicCompletion.objects.filter(user=user).select_related("topic", "topic__subject")
    for tc in topic_comps:
        best_sc = float(tc.best_score or 0)
        pct = round((best_sc / 16.0) * 100, 1)
        if pct < 60.0:
            weak_topics.append({
                "topic": tc.topic,
                "subject": tc.topic.subject,
                "best_score": best_sc,
                "percentage": pct,
            })

    # Personal Target
    personal_target, _ = PersonalTarget.objects.get_or_create(
        user=user,
        track=None,
        defaults={"target_percentage": Decimal("75.00")}
    )
    target_score = float(personal_target.target_percentage)
    target_gap = round(avg_score_pct - target_score, 2)

    # Attempt Progression Trend
    attempts_by_number = {}
    for r in results:
        att_num = r.attempt.attempt_number
        if att_num not in attempts_by_number:
            attempts_by_number[att_num] = []
        attempts_by_number[att_num].append(float(r.score_percentage))

    progression_trend = [
        {"attempt": k, "avg_score_pct": round(sum(v) / len(v), 1), "tests_count": len(v)}
        for k, v in sorted(attempts_by_number.items())
    ]

    context = {
        "total_tests_taken": total_tests_taken,
        "avg_score_pct": avg_score_pct,
        "avg_accuracy_pct": avg_accuracy_pct,
        "avg_completion_pct": avg_completion_pct,
        "total_qs_solved": total_qs_solved,
        "subject_analytics": subject_analytics,
        "weak_topics": weak_topics,
        "personal_target": personal_target,
        "target_score": target_score,
        "target_gap": target_gap,
        "progression_trend": progression_trend,
    }
    return render(request, "assessments/analytics_dashboard.html", context)


# ==============================================================================
# 7. PERSONAL TARGET API (SECTION 14)
# ==============================================================================

@login_required
def personal_target_set_view(request):
    """
    Sets or updates the candidate's personal target percentage (50% to 100%).
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else request.POST
        target_val = float(data.get("target_percentage", 75.0))
        target_val = max(50.0, min(100.0, target_val))
    except Exception:
        target_val = 75.0

    target_obj, _ = PersonalTarget.objects.update_or_create(
        user=request.user,
        track=None,
        defaults={
            "target_percentage": Decimal(str(round(target_val, 2))),
        }
    )

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "target": float(target_obj.target_percentage)})
    
    messages.success(request, f"Personal target updated to {target_obj.target_percentage}%.")
    return redirect("performance_analytics")


# ==============================================================================
# 8. ADMINISTRATIVE QUESTION BANK & AUDIT (SECTION 15 & 17)
# ==============================================================================

@owner_required
def admin_question_management_view(request):
    """
    Administrative Question Bank Management Portal:
    - Filter by Track (MCA, MBA), Subject, Topic, Difficulty, and Verification Status
    - Verify, Reject, or Archive questions with audit logging
    - View duplicate fingerprints and question shortage reports
    """
    track_code = request.GET.get("track", "").strip().upper()
    subj_id = request.GET.get("subject", "").strip()
    status_filter = request.GET.get("status", "").strip().upper()
    verified_filter = request.GET.get("verified", "").strip()

    questions_qs = Question.objects.select_related("subject", "topic", "subject__entrance_track").order_by("-id")

    if track_code:
        questions_qs = questions_qs.filter(subject__entrance_track__code=track_code)
    if subj_id:
        questions_qs = questions_qs.filter(subject_id=subj_id)
    if status_filter:
        questions_qs = questions_qs.filter(status=status_filter)
    if verified_filter == "1":
        questions_qs = questions_qs.filter(is_verified=True)
    elif verified_filter == "0":
        questions_qs = questions_qs.filter(is_verified=False)

    paginator = Paginator(questions_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    # Audit history
    recent_audits = AdminReviewHistory.objects.select_related("admin_user", "question").order_by("-reviewed_at")[:15]

    context = {
        "questions": page_obj,
        "tracks": EntranceTrack.objects.all(),
        "subjects": Subject.objects.all().order_by("name"),
        "total_count": questions_qs.count(),
        "verified_count": Question.objects.filter(is_verified=True).count(),
        "recent_audits": recent_audits,
        "active_track": track_code,
        "active_subject": subj_id,
        "active_status": status_filter,
        "active_verified": verified_filter,
    }
    return render(request, "assessments/admin_question_hub.html", context)


@owner_required
def admin_attempt_reset_view(request):
    """
    Authorized administrative reset of candidate attempts with audit record.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    exam_id = request.POST.get("exam_id")
    target_user_id = request.POST.get("user_id")
    reason = request.POST.get("reason", "").strip()

    if not reason:
        messages.error(request, "Administrative reset requires an explicit audit reason.")
        return redirect("admin_assessment_hub")

    from django.contrib.auth import get_user_model
    User = get_user_model()
    target_user = get_object_or_404(User, id=target_user_id)
    exam = get_object_or_404(Examination, id=exam_id)

    with transaction.atomic():
        deleted_count = ExamAttempt.objects.filter(user=target_user, examination=exam).delete()[0]
        # Clear candidate question exposure for this exam
        UserQuestionHistory.objects.filter(user=target_user, examination=exam).delete()
        # Reset topic completion
        if exam.topic:
            TopicCompletion.objects.filter(user=target_user, topic=exam.topic).delete()
            TopicProgress.objects.filter(user=target_user, topic=exam.topic).delete()

        AdminReviewHistory.objects.create(
            admin_user=request.user,
            action_type="ATTEMPT_RESET",
            comments=f"Reset {deleted_count} attempts for candidate '{target_user.username}' on '{exam.title}'. Reason: {reason}"
        )

    messages.success(request, f"Successfully reset attempts for {target_user.username} on '{exam.title}'.")
    return redirect("admin_assessment_hub")


# ==============================================================================
# 9. INTELLIGENT AI EDUCATIONAL ASSISTANT (SECTION 13)
# ==============================================================================

def ai_educational_assistant_view(request):
    """
    Intelligent AI Educational Assistant:
    - Explains theoretical concepts in depth
    - Step-by-step mathematical problem solver
    - Exam mistake analysis and misconception diagnosis
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else request.POST
        prompt = (data.get("prompt") or "").strip()
        topic_name = (data.get("topic") or "").strip()
        subject_name = (data.get("subject") or "").strip()
    except Exception:
        prompt = ""
        topic_name = ""
        subject_name = ""

    if not prompt and not topic_name:
        return JsonResponse({"success": False, "error": "Prompt or topic required."}, status=400)

    # Use AIQuestionEngine to generate pedagogical explanation
    try:
        answer = AIQuestionEngine.generate_conceptual_explanation(
            topic_name=topic_name or "General CS",
            subject_name=subject_name or "Entrance Prep",
            user_query=prompt
        )
    except Exception as e:
        answer = (
            f"### Conceptual Analysis: {topic_name or 'Entrance Invariants'}\n"
            f"1. **Core Principle**: In competitive entrance preparation, verify boundary constraints first.\n"
            f"2. **Problem-Solving Strategy**: Eliminate distractors violating fundamental theorems.\n"
            f"3. **Step-by-Step Breakdown**: Apply definitions strictly from first principles to isolate the target variable."
        )

    return JsonResponse({"success": True, "explanation": answer})

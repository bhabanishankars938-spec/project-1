import json
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from .models import (
    Question, Examination, ExamAttempt, ExamResponse,
    CodingProblem, CodingSubmission, Subject, Topic
)
from .sandbox import evaluate_submission_against_problem, SecureExecutionSandbox
from .services import ExamEvaluationService, AIQuestionEngine

logger = logging.getLogger(__name__)


@require_POST
def api_exam_save_answer(request, attempt_id):
    """
    AJAX endpoint invoked on answer select, text change, or navigation.
    Synchronizes response and returns remaining time.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)

    attempt = get_object_or_404(ExamAttempt, id=attempt_id, user=request.user)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    question_id = data.get("question_id")
    selected_option_ids = data.get("selected_option_ids", [])
    text_answer = data.get("text_answer", "")
    is_marked = data.get("is_marked_for_review", False)
    time_spent = data.get("time_spent_seconds", 0)

    if not question_id:
        return JsonResponse({"success": False, "error": "question_id is required"}, status=400)

    res = ExamEvaluationService.save_candidate_response(
        attempt=attempt,
        question_id=int(question_id),
        selected_option_ids=selected_option_ids,
        text_answer=text_answer,
        is_marked_for_review=bool(is_marked),
        time_spent_seconds=int(time_spent) if str(time_spent).isdigit() else 0,
    )
    return JsonResponse(res)


@require_POST
def api_exam_submit(request, attempt_id):
    """
    Finalizes examination attempt and computes all marks and analytics.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)

    attempt = get_object_or_404(ExamAttempt, id=attempt_id, user=request.user)
    finalized = ExamEvaluationService.finalize_submission(attempt, auto_timed_out=False)

    return JsonResponse({
        "success": True,
        "score": float(finalized.score),
        "percentage": float(finalized.percentage),
        "passed": finalized.passed,
        "total_questions": finalized.total_questions,
        "correct_count": finalized.correct_count,
        "incorrect_count": finalized.incorrect_count,
        "skipped_count": finalized.skipped_count,
        "redirect_url": f"/assessments/exams/results/{finalized.id}/",
    })


@require_POST
def api_code_run(request):
    """
    Executes user code against sample test cases or custom input in sandbox.
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    problem_id = data.get("problem_id")
    language = data.get("language", "python")
    code = data.get("code", "")
    custom_input = data.get("custom_input", None)
    use_custom = data.get("use_custom_input", False)

    if not code:
        return JsonResponse({"success": False, "error": "No code provided"}, status=400)

    if problem_id:
        problem = get_object_or_404(CodingProblem, id=problem_id)
        c_in = custom_input if use_custom else None
        res = evaluate_submission_against_problem(problem, code, language, custom_input=c_in, is_submit=False)
        return JsonResponse(res)
    else:
        # Standalone runner
        exec_res = SecureExecutionSandbox.execute_code(language, code, input_data=custom_input or "", time_limit=3.0)
        return JsonResponse({
            "mode": "standalone",
            "status": exec_res["status"],
            "stdout": exec_res["output"],
            "stderr": exec_res["error"],
            "runtime_ms": exec_res["runtime_ms"],
        })


@require_POST
def api_code_submit(request):
    """
    Submits user code for full evaluation against all public and hidden test cases.
    Saves a persistent CodingSubmission record.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    problem_id = data.get("problem_id")
    language = data.get("language", "python")
    code = data.get("code", "")

    if not problem_id or not code:
        return JsonResponse({"success": False, "error": "problem_id and code are required"}, status=400)

    problem = get_object_or_404(CodingProblem, id=problem_id)
    eval_res = evaluate_submission_against_problem(problem, code, language, is_submit=True)

    status_map = {
        "ACCEPTED": CodingSubmission.Status.ACCEPTED,
        "WRONG_ANSWER": CodingSubmission.Status.WRONG_ANSWER,
        "TIME_LIMIT_EXCEEDED": CodingSubmission.Status.TIME_LIMIT,
        "COMPILATION_ERROR": CodingSubmission.Status.COMPILE_ERROR,
        "RUNTIME_ERROR": CodingSubmission.Status.RUNTIME_ERROR,
    }
    db_status = status_map.get(eval_res["status"], CodingSubmission.Status.RUNTIME_ERROR)

    submission = CodingSubmission.objects.create(
        user=request.user,
        problem=problem,
        language=language,
        code=code,
        status=db_status,
        passed_cases_count=eval_res["passed_count"],
        total_cases_count=eval_res["total_count"],
        execution_time_ms=eval_res["runtime_ms"],
        error_message=eval_res.get("stderr", ""),
    )

    # Update student skill mastery
    if problem.subject:
        from .models import StudentSkillMastery
        mastery, _ = StudentSkillMastery.objects.get_or_create(user=request.user, subject=problem.subject)
        if db_status == CodingSubmission.Status.ACCEPTED:
            mastery.coding_solved_count += 1
            mastery.save(update_fields=["coding_solved_count"])
        ExamEvaluationService.recalculate_placement_readiness(request.user)

    return JsonResponse({
        "success": True,
        "submission_id": submission.id,
        "status": eval_res["status"],
        "passed_count": eval_res["passed_count"],
        "total_count": eval_res["total_count"],
        "runtime_ms": eval_res["runtime_ms"],
        "test_results": eval_res["test_results"],
        "stderr": eval_res.get("stderr", ""),
    })


@require_POST
def api_ai_explain(request):
    """
    Provides step-by-step AI explanation and misconception breakdown for any question.
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    question_id = data.get("question_id")
    user_answer = data.get("user_answer", "")

    if not question_id:
        return JsonResponse({"success": False, "error": "question_id required"}, status=400)

    question = get_object_or_404(Question, id=question_id)
    res = AIQuestionEngine.generate_ai_explanation_for_response(question, user_answer)
    return JsonResponse(res)


@require_POST
def api_ai_generate_questions(request):
    """
    Admin-accessible AI generation endpoint with schema validation and draft creation.
    """
    if not request.user.is_authenticated or not (request.user.is_owner or request.user.is_staff):
        return JsonResponse({"success": False, "error": "Unauthorized access"}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    subject_id = data.get("subject_id")
    topic_name = data.get("topic_name", "")
    difficulty = data.get("difficulty", "BEGINNER")
    question_type = data.get("question_type", "MCQ")
    count = int(data.get("count", 3))
    target_exam = data.get("target_exam", "")

    subject = get_object_or_404(Subject, id=subject_id)

    generated_raw = AIQuestionEngine.generate_questions_batch(
        subject_name=subject.name,
        topic_name=topic_name,
        difficulty=difficulty,
        question_type=question_type,
        count=min(10, max(1, count)),
        target_exam=target_exam,
        user=request.user,
    )

    if not generated_raw:
        return JsonResponse({"success": False, "error": "AI provider was unable to generate questions or output schema was invalid."}, status=500)

    # Save to review queue
    created_items = []
    for item in generated_raw:
        title = item.get("title", f"Generated {subject.name} Question")
        q = Question.objects.create(
            subject=subject,
            question_type=question_type,
            difficulty=difficulty,
            title=title,
            question_text=item.get("question_text", ""),
            code_snippet=item.get("code_snippet", ""),
            marks=float(item.get("marks", 1.0)),
            negative_marks=float(item.get("negative_marks", 0.25)),
            status=Question.Status.AI_GENERATED,
            verification_certainty=0.90,
            created_by=request.user,
        )
        for opt in item.get("options", []):
            q.options.create(
                option_key=opt.get("key", "A"),
                option_text=opt.get("text", ""),
                is_correct=bool(opt.get("is_correct", False)),
                explanation=opt.get("explanation", ""),
            )
        exp = item.get("explanation", {})
        if exp:
            q.explanation_detail = QuestionExplanation.objects.create(
                question=q,
                correct_answer_summary=exp.get("correct_answer_summary", ""),
                why_correct=exp.get("why_correct", ""),
                why_others_incorrect=exp.get("why_others_incorrect", ""),
                step_by_step_logic=exp.get("step_by_step_logic", ""),
                practical_example=exp.get("practical_example", ""),
            )
        created_items.append({
            "id": q.id,
            "title": q.title,
            "status": q.status,
            "options_count": q.options.count(),
        })

    return JsonResponse({
        "success": True,
        "count": len(created_items),
        "questions": created_items,
        "message": f"Successfully generated {len(created_items)} questions and queued for admin verification.",
    })

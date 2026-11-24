import logging
from collections import defaultdict
from datetime import timedelta
from typing import Dict, Any, List, Optional
from django.utils import timezone
from accounts.models import User
from assessments.models import (
    Subject,
    Topic,
    Question,
    QuestionExplanation,
    ExamAttempt,
    ExamResponse,
    Result,
    TopicProgress,
    LearningNote,
)

logger = logging.getLogger(__name__)


class ExamCoachService:
    """
    Intelligent Examination Coach for HireNexa candidates.
    Delivers weak topic detection, mistake analysis, verified concept revision,
    and adaptive personalized practice quizzes.
    """

    @classmethod
    def get_coach_insights(cls, user: User) -> Dict[str, Any]:
        """Gathers comprehensive diagnostic intelligence for candidate exam preparation."""
        weak_topics = cls.detect_weak_topics(user)
        mistake_analysis = cls.analyze_recent_mistakes(user)
        performance_trend = cls.get_performance_trends(user)
        revision_reminders = cls.get_revision_reminders(user)

        return {
            "weak_topics": weak_topics,
            "mistakes_analyzed": mistake_analysis,
            "performance_trend": performance_trend,
            "revision_reminders": revision_reminders,
            "has_history": len(performance_trend["history"]) > 0,
        }

    @classmethod
    def detect_weak_topics(cls, user: User) -> List[Dict[str, Any]]:
        """
        Detects topics where candidate accuracy or mastery is below 60%,
        or where high incorrect response count is detected.
        """
        weak_list = []

        # 1. From TopicProgress records
        low_mastery = TopicProgress.objects.filter(
            user=user, mastery_percentage__lt=60, attempts_count__gt=0
        ).select_related("topic", "topic__subject").order_by("mastery_percentage")

        for p in low_mastery[:6]:
            weak_list.append({
                "topic_id": p.topic.id,
                "topic_name": p.topic.name,
                "subject_id": p.topic.subject.id,
                "subject_name": p.topic.subject.name,
                "mastery_percentage": float(p.mastery_percentage),
                "attempts_count": p.attempts_count,
                "urgency": "CRITICAL" if p.mastery_percentage < 40 else "MODERATE",
                "recommendation": f"Current mastery {p.mastery_percentage:.1f}%. Recommended 5-question adaptive drill.",
            })

        # 2. From recent ExamResponse incorrect answers
        if len(weak_list) < 3:
            recent_incorrect = ExamResponse.objects.filter(
                attempt__user=user, is_correct=False
            ).select_related("question__topic", "question__subject")[:20]

            topic_errors = defaultdict(int)
            topic_subject_map = {}
            for resp in recent_incorrect:
                if resp.question and resp.question.topic:
                    t_id = resp.question.topic.id
                    topic_errors[t_id] += 1
                    topic_subject_map[t_id] = (resp.question.topic.name, resp.question.subject.name, resp.question.subject.id)

            for t_id, err_cnt in sorted(topic_errors.items(), key=lambda x: x[1], reverse=True)[:3]:
                if not any(w["topic_id"] == t_id for w in weak_list):
                    t_name, s_name, s_id = topic_subject_map[t_id]
                    weak_list.append({
                        "topic_id": t_id,
                        "topic_name": t_name,
                        "subject_id": s_id,
                        "subject_name": s_name,
                        "mastery_percentage": max(20.0, 60.0 - (err_cnt * 10)),
                        "attempts_count": err_cnt,
                        "urgency": "MODERATE",
                        "recommendation": f"{err_cnt} recent errors recorded. Review explanation notes before retesting.",
                    })

        return weak_list

    @classmethod
    def analyze_recent_mistakes(cls, user: User, limit: int = 4) -> List[Dict[str, Any]]:
        """
        Analyzes recent incorrect candidate responses, pairing them with verified
        explanations, step-by-step logic, and misconception warnings.
        """
        mistakes = []
        incorrect_responses = ExamResponse.objects.filter(
            attempt__user=user, is_correct=False
        ).select_related("question", "question__subject", "question__topic", "attempt__examination").order_by("-answered_at")[:limit]

        for resp in incorrect_responses:
            q = resp.question
            explanation_obj = getattr(q, "explanation_detail", None)

            correct_opts = q.options.filter(is_correct=True)
            correct_text = ", ".join([f"[{o.option_key}] {o.option_text}" for o in correct_opts])

            # Get user's selected option texts
            selected_opts = q.options.filter(id__in=resp.selected_option_ids)
            selected_text = ", ".join([f"[{o.option_key}] {o.option_text}" for o in selected_opts]) if selected_opts.exists() else (resp.text_answer or "No option selected")

            why_wrong = ""
            why_correct = q.explanation or ""
            step_logic = ""

            if explanation_obj:
                why_wrong = explanation_obj.why_others_incorrect or ""
                why_correct = explanation_obj.why_correct or q.explanation
                step_logic = explanation_obj.step_by_step_logic or ""

            mistakes.append({
                "question_id": q.id,
                "title": q.title,
                "exam_title": resp.attempt.examination.title,
                "subject_name": q.subject.name,
                "topic_name": q.topic.name if q.topic else "",
                "question_text": q.question_text,
                "user_answer": selected_text,
                "correct_answer": correct_text,
                "why_correct": why_correct,
                "why_incorrect": why_wrong or "Common misconception in core concept application.",
                "step_by_step_logic": step_logic,
            })

        return mistakes

    @classmethod
    def get_concept_revision(cls, topic_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves comprehensive verified learning notes and high-yield formulas for a topic."""
        note = LearningNote.objects.filter(topic_id=topic_id).select_related("topic", "subject").first()
        if not note:
            # Fallback to basic topic description
            topic = Topic.objects.filter(id=topic_id).first()
            if not topic:
                return None
            return {
                "topic_id": topic.id,
                "topic_name": topic.name,
                "subject_name": topic.subject.name,
                "concept_summary": topic.description or "Fundamental concepts for this syllabus unit.",
                "detailed_explanation": "Review curriculum syllabus guidelines and verified practice problems.",
                "quick_formulas": [],
                "common_pitfalls": "Ensure clarity between edge-case conditions and baseline definitions.",
            }

        return {
            "topic_id": note.topic.id,
            "topic_name": note.topic.name,
            "subject_name": note.subject.name,
            "concept_summary": note.concept_summary,
            "detailed_explanation": note.detailed_explanation,
            "quick_formulas": note.quick_revision_formulas,
            "common_pitfalls": note.common_pitfalls,
            "comparison_table": note.comparison_table_markdown,
        }

    @classmethod
    def get_performance_trends(cls, user: User) -> Dict[str, Any]:
        """Calculates historical score progression across test attempts."""
        results = Result.objects.filter(user=user).select_related("examination").order_by("created_at")[:12]
        history = []
        for r in results:
            history.append({
                "exam_title": r.examination.title,
                "score_pct": float(r.score_percentage),
                "accuracy_pct": float(r.accuracy_percentage),
                "passed": r.is_passed,
                "date": r.created_at.strftime("%b %d"),
            })

        avg_score = round(sum(h["score_pct"] for h in history) / max(1, len(history)), 1)
        latest_score = history[-1]["score_pct"] if history else 0.0

        trend_status = "STABLE"
        if len(history) >= 2:
            if history[-1]["score_pct"] > history[-2]["score_pct"]:
                trend_status = "IMPROVING"
            elif history[-1]["score_pct"] < history[-2]["score_pct"]:
                trend_status = "DECLINING"

        return {
            "history": history,
            "average_score": avg_score,
            "latest_score": latest_score,
            "trend_status": trend_status,
            "total_attempts": len(history),
        }

    @classmethod
    def get_revision_reminders(cls, user: User) -> List[Dict[str, Any]]:
        """Identifies topics studied or attempted more than 5 days ago that need reinforcement."""
        stale_date = timezone.now() - timedelta(days=5)
        reminders = []

        progress_qs = TopicProgress.objects.filter(
            user=user, last_attempted_at__lte=stale_date
        ).select_related("topic", "topic__subject").order_by("last_attempted_at")[:4]

        for p in progress_qs:
            days_ago = (timezone.now() - p.last_attempted_at).days if p.last_attempted_at else 7
            reminders.append({
                "topic_id": p.topic.id,
                "topic_name": p.topic.name,
                "subject_name": p.topic.subject.name,
                "days_since_practice": days_ago,
                "mastery_score": float(p.mastery_percentage),
                "message": f"Last practiced {days_ago} days ago. Spaced repetition review is recommended.",
            })

        return reminders

    @classmethod
    def generate_adaptive_practice_questions(
        cls, user: User, topic_id: Optional[int] = None, num_questions: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Dynamically selects verified syllabus questions targeting the candidate's weak topics.
        Ensures all questions have verified answers and explanations.
        """
        qs = Question.objects.filter(status=Question.Status.APPROVED, is_verified=True)

        if topic_id:
            qs = qs.filter(topic_id=topic_id)
        else:
            weak_topics = cls.detect_weak_topics(user)
            if weak_topics:
                target_ids = [w["topic_id"] for w in weak_topics]
                qs = qs.filter(topic_id__in=target_ids)

        selected_questions = list(qs.select_related("subject", "topic").prefetch_related("options")[:num_questions])

        formatted = []
        for q in selected_questions:
            options_data = [
                {"id": opt.id, "key": opt.option_key, "text": opt.option_text, "is_correct": opt.is_correct}
                for opt in q.options.all()
            ]
            formatted.append({
                "id": q.id,
                "title": q.title,
                "subject": q.subject.name,
                "topic": q.topic.name if q.topic else "",
                "difficulty": q.get_difficulty_display(),
                "text": q.question_text,
                "options": options_data,
                "explanation": q.explanation,
            })

        return formatted

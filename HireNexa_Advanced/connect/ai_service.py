import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Standard curated technical question bank fallback by domain
CURATED_TECHNICAL_QUESTIONS = {
    "backend": [
        {"q": "How would you design a distributed rate-limiter that works across multiple server instances?", "difficulty": "Advanced", "competency": "System Design"},
        {"q": "Explain database indexing strategies (B-Tree vs Hash) and how they impact write-heavy vs read-heavy workloads.", "difficulty": "Intermediate", "competency": "Database Architecture"},
        {"q": "How do you handle idempotency in asynchronous payment processing or webhook consumption?", "difficulty": "Advanced", "competency": "API Design & Resiliency"},
        {"q": "Explain the difference between concurrency and parallelism with examples in Python or Go.", "difficulty": "Intermediate", "competency": "Core Computer Science"},
        {"q": "How do you detect and prevent race conditions and deadlocks in multi-threaded database transactions?", "difficulty": "Advanced", "competency": "Concurrency & Safety"},
    ],
    "frontend": [
        {"q": "Explain the browser critical rendering path and specific techniques to improve Largest Contentful Paint (LCP).", "difficulty": "Advanced", "competency": "Web Performance"},
        {"q": "How does React Fiber reconciliation algorithm handle priority rendering and interruptible updates?", "difficulty": "Advanced", "competency": "Frontend Frameworks"},
        {"q": "Compare WebRTC P2P mesh, MCU, and SFU architectures for real-time video conferencing.", "difficulty": "Advanced", "competency": "Real-Time Web Technologies"},
        {"q": "Explain state management tradeoffs between localized component state, Context API, and state machines.", "difficulty": "Intermediate", "competency": "Architecture & State"},
    ],
    "fullstack": [
        {"q": "Walk through an end-to-end user request lifecycle from DNS lookup to database query and response rendering.", "difficulty": "Intermediate", "competency": "Systems Understanding"},
        {"q": "How do you architect secure authentication with short-lived JWTs, HTTP-only refresh cookies, and CSRF protection?", "difficulty": "Advanced", "competency": "Application Security"},
        {"q": "How do you manage database schema migrations without downtime in high-availability services?", "difficulty": "Advanced", "competency": "DevOps & Infrastructure"},
    ],
    "hr": [
        {"q": "Describe a high-impact technical challenge you solved where requirements were ambiguous. How did you align stakeholders?", "difficulty": "Standard", "competency": "Collaboration & Problem Solving"},
        {"q": "Tell me about a time you identified technical debt that was slowing the team down. How did you prioritize and execute the refactor?", "difficulty": "Standard", "competency": "Engineering Ownership"},
        {"q": "How do you approach mentoring junior team members while maintaining your own individual sprint deliverables?", "difficulty": "Standard", "competency": "Leadership & Mentorship"},
    ]
}


class AIInterviewIntelligenceService:
    """
    AI-powered interview intelligence engine.
    Adheres strictly to HireNexa Ethical AI Principles:
    - Never makes automated hiring or rejection decisions.
    - No biometric, facial, or accent analysis.
    - All suggestions are transparent, explainable, and reviewed by human interviewers.
    - Gracefully falls back to curated expert banks when AI services are offline.
    """

    @classmethod
    def generate_interview_questions(
        cls,
        job_title: str,
        job_description: str = "",
        candidate_skills: List[str] = None,
        round_name: str = "Technical Round"
    ) -> Dict[str, Any]:
        """
        Generates structured interview questions categorized into core technical competencies,
        system design, situational problem solving, and role-specific requirements.
        """
        skills_str = ", ".join(candidate_skills) if candidate_skills else "General Software Engineering"
        
        # Check if AIAssistantService is available in ai_assistant app
        try:
            from ai_assistant.services import AIAssistantService
            prompt = (
                f"You are an expert technical interviewer assistant. Generate 5 structured interview questions "
                f"for a '{round_name}' for the position of '{job_title}'.\n"
                f"Job Description Excerpt: {job_description[:500]}\n"
                f"Key Candidate Skills: {skills_str}\n\n"
                f"Format response as a JSON array of objects with keys: 'question', 'topic', 'difficulty', 'what_to_look_for'.\n"
                f"Do not make hiring decisions or evaluate personality. Return only valid JSON."
            )
            # Try AI generation
            res = AIAssistantService.generate_response(prompt)
            if res and ("[" in res and "]" in res):
                start = res.find("[")
                end = res.rfind("]") + 1
                questions = json.loads(res[start:end])
                return {
                    "success": True,
                    "provider": "HireNexa AI Engine",
                    "questions": questions,
                    "disclaimer": "AI suggestions are meant to assist the human interviewer. Final hiring decisions rest solely with authorized human evaluators."
                }
        except Exception as e:
            logger.info("AI Provider unavailable, using curated interview intelligence bank: %s", e)

        # Resilient Fallback to Curated Domain Bank
        lower_title = job_title.lower()
        if "frontend" in lower_title or "ui" in lower_title or "react" in lower_title:
            bank = CURATED_TECHNICAL_QUESTIONS["frontend"]
        elif "backend" in lower_title or "python" in lower_title or "django" in lower_title:
            bank = CURATED_TECHNICAL_QUESTIONS["backend"]
        elif "hr" in round_name.lower() or "behavioral" in round_name.lower():
            bank = CURATED_TECHNICAL_QUESTIONS["hr"]
        else:
            bank = CURATED_TECHNICAL_QUESTIONS["fullstack"]

        questions = [
            {
                "question": item["q"],
                "topic": item["competency"],
                "difficulty": item["difficulty"],
                "what_to_look_for": "Clarity of thought, real-world experience, architectural trade-offs, and edge case awareness."
            }
            for item in bank
        ]

        return {
            "success": True,
            "provider": "HireNexa Curated Question Intelligence",
            "questions": questions,
            "disclaimer": "Standardized expert questions curated for standardized recruitment evaluation."
        }

    @classmethod
    def generate_meeting_summary(
        cls,
        meeting_title: str,
        rough_notes: str,
        round_name: str = "Technical"
    ) -> Dict[str, Any]:
        """
        Synthesizes rough in-meeting notes into an organized interview summary with
        demonstrated strengths, areas for deep dive, and recommended next steps.
        """
        if not rough_notes or len(rough_notes.strip()) < 10:
            return {
                "success": False,
                "error": "Please provide interview notes to generate a structured evaluation summary."
            }

        try:
            from ai_assistant.services import AIAssistantService
            prompt = (
                f"You are a talent evaluation assistant. Summarize the following interview notes for '{meeting_title}' ({round_name}):\n\n"
                f"Notes: {rough_notes}\n\n"
                f"Generate a professional structured evaluation summary with:\n"
                f"1. Executive Summary\n"
                f"2. Core Strengths Observed\n"
                f"3. Potential Technical Gaps / Follow-ups\n"
                f"4. Suggested Topics for Next Round\n\n"
                f"Do not render final pass/fail decisions. Keep language objective and evidence-based."
            )
            res = AIAssistantService.generate_response(prompt)
            if res:
                return {
                    "success": True,
                    "summary": res,
                    "provider": "HireNexa AI Engine"
                }
        except Exception as e:
            logger.info("AI Provider unavailable for summary, using heuristic synthesizer: %s", e)

        # Fallback heuristic summary
        summary = (
            f"### Interview Evaluation Synthesis: {meeting_title}\n\n"
            f"**Round:** {round_name}\n\n"
            f"**Key Notes Captured:**\n"
            f"{rough_notes.strip()}\n\n"
            f"**Assessment Checklist:**\n"
            f"- Technical Competency & Code Quality: Evaluated per rubric.\n"
            f"- Problem Solving & Communication: Review interviewer scorecard.\n"
            f"- Follow-up: Cross-reference candidate's portfolio and assessment test scores.\n\n"
            f"*Note: Explainable evaluation summary compiled by HireNexa Intelligence.*"
        )
        return {
            "success": True,
            "summary": summary,
            "provider": "HireNexa Evaluation Synthesizer"
        }

import logging
from typing import Dict, Any, List, Optional
from django.db.models import Q
from accounts.models import User
from recruitment.models import Job, CandidateProfile, CandidateSkill, Resume

logger = logging.getLogger(__name__)


class IntelligentJobDiscoveryEngine:
    """
    Intelligent Job Discovery & Explainable Recommendation Engine.
    Matches candidates to vacancies by scoring:
      - Skill overlap (40%)
      - Target role/title alignment (20%)
      - Experience level suitability (15%)
      - Preferred work mode (15%)
      - Location proximity/match (10%)
    Supports candidate interactive preference tuning with transparent reasons.
    """

    @classmethod
    def get_candidate_preferences(cls, user: User) -> Dict[str, Any]:
        """Loads candidate baseline profile & saved preferences."""
        profile = getattr(user, "candidate_profile", None)
        user_skills = list(
            CandidateSkill.objects.filter(candidate=user).values_list("name", flat=True)
        )

        if profile and profile.skills:
            for s in profile.skills.split(","):
                clean = s.strip()
                if clean and clean.lower() not in [x.lower() for x in user_skills]:
                    user_skills.append(clean)

        preferred_locations = profile.preferred_locations if profile else []
        preferred_work_mode = profile.preferred_work_mode if profile else "ALL"
        target_role = profile.headline.split("|")[0].strip() if (profile and profile.headline) else ""

        # Experience calculation
        experience_years = 0.0
        skills_exp = CandidateSkill.objects.filter(candidate=user).values_list("years_of_experience", flat=True)
        if skills_exp:
            experience_years = max(skills_exp)

        return {
            "skills": user_skills,
            "target_role": target_role,
            "preferred_locations": preferred_locations or [profile.location] if (profile and profile.location) else [],
            "preferred_work_mode": preferred_work_mode,
            "experience_years": experience_years,
            "education": profile.education if profile else "",
        }

    @classmethod
    def discover_jobs(
        cls,
        user: Optional[User] = None,
        preferences_override: Optional[Dict[str, Any]] = None,
        limit: int = 12,
    ) -> Dict[str, Any]:
        """
        Discovers and ranks active jobs matching candidate preferences.
        Returns recommendations with individual component score breakdowns.
        """
        base_prefs = cls.get_candidate_preferences(user) if (user and user.is_authenticated) else {
            "skills": [],
            "target_role": "",
            "preferred_locations": [],
            "preferred_work_mode": "ALL",
            "experience_years": 0.0,
            "education": "",
        }

        # Apply user overrides from discovery search UI
        prefs = dict(base_prefs)
        if preferences_override:
            for k, v in preferences_override.items():
                if v is not None and v != "":
                    prefs[k] = v

        user_skills_lower = set(s.lower().strip() for s in prefs.get("skills", []))
        override_work_mode = prefs.get("preferred_work_mode", "ALL")
        override_locations = [l.lower().strip() for l in prefs.get("preferred_locations", []) if l]
        override_role = (prefs.get("target_role") or "").lower().strip()
        candidate_exp = float(prefs.get("experience_years", 0.0))

        active_jobs = Job.objects.filter(is_active=True, status=Job.Status.ACTIVE).select_related("organization")
        scored_jobs = []

        for job in active_jobs:
            job_skills = job.skill_list()
            
            # 1. Skill Score (Max 40 pts)
            matched_skills = [s for s in job_skills if s in user_skills_lower]
            missing_skills = [s for s in job_skills if s not in user_skills_lower]
            skill_score = (len(matched_skills) / max(1, len(job_skills))) * 40.0 if job_skills else 20.0

            # 2. Target Role Score (Max 20 pts)
            role_score = 0.0
            if override_role:
                if override_role in job.title.lower() or any(w in job.title.lower() for w in override_role.split() if len(w) > 3):
                    role_score = 20.0
                elif any(w in job.description.lower() for w in override_role.split() if len(w) > 3):
                    role_score = 10.0
            else:
                role_score = 15.0  # Neutral baseline

            # 3. Work Mode Score (Max 15 pts)
            work_mode_score = 0.0
            job_wm = job.workplace_type.upper()
            if override_work_mode == "ALL":
                work_mode_score = 15.0
            elif override_work_mode.upper() in job_wm:
                work_mode_score = 15.0
            elif job_wm == "REMOTE":
                work_mode_score = 12.0  # Remote is flexible
            else:
                work_mode_score = 5.0

            # 4. Location Score (Max 10 pts)
            location_score = 0.0
            job_loc = (job.location or "").lower()
            if not override_locations or job_wm == "REMOTE":
                location_score = 10.0
            elif any(loc in job_loc or loc in (job.city or "").lower() for loc in override_locations):
                location_score = 10.0
            elif any(loc in (job.state or "").lower() for loc in override_locations):
                location_score = 7.0
            else:
                location_score = 3.0

            # 5. Experience Suitability (Max 15 pts)
            exp_diff = abs(job.min_experience_years - candidate_exp)
            if exp_diff <= 1:
                exp_score = 15.0
            elif exp_diff <= 2:
                exp_score = 10.0
            else:
                exp_score = 5.0

            total_score = round(skill_score + role_score + work_mode_score + location_score + exp_score, 1)

            # Build explainability rationale
            reasons = []
            if matched_skills:
                reasons.append(f"Matching skills: {', '.join([s.title() for s in matched_skills[:3]])}")
            if override_work_mode != "ALL" and override_work_mode.upper() in job_wm:
                reasons.append(f"Matches your '{job.get_workplace_type_display()}' work mode preference")
            if location_score >= 7.0 and job_wm != "REMOTE":
                reasons.append(f"Location in {job.location or job.city}")
            elif job_wm == "REMOTE":
                reasons.append("100% Remote flexibility")
            if exp_score >= 10:
                reasons.append(f"Experience required ({job.min_experience_years} yrs) aligns with your profile")

            salary_display = "Industry Standard"
            if job.display_salary_publicly and job.salary_min and job.salary_max:
                salary_display = f"₹{job.salary_min:,.0f} - ₹{job.salary_max:,.0f}"
            elif job.display_salary_publicly and job.salary_min:
                salary_display = f"₹{job.salary_min:,.0f}+"

            scored_jobs.append({
                "job_id": job.id,
                "title": job.title,
                "company_name": job.company_name,
                "location": job.location or "Remote",
                "city": job.city,
                "state": job.state,
                "workplace_type": job.get_workplace_type_display(),
                "job_type": job.get_job_type_display(),
                "salary": salary_display,
                "vacancies": job.vacancies,
                "total_score": min(100.0, total_score),
                "breakdown": {
                    "skill_score": round(skill_score, 1),
                    "role_score": round(role_score, 1),
                    "work_mode_score": round(work_mode_score, 1),
                    "location_score": round(location_score, 1),
                    "experience_score": round(exp_score, 1),
                },
                "matched_skills": [s.title() for s in matched_skills],
                "missing_skills": [s.title() for s in missing_skills],
                "reasons": reasons,
                "apply_url": f"/jobs/{job.id}/",
            })

        scored_jobs.sort(key=lambda x: x["total_score"], reverse=True)

        return {
            "applied_preferences": prefs,
            "total_matches": len(scored_jobs),
            "recommendations": scored_jobs[:limit],
        }

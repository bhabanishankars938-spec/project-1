import logging
from collections import Counter
from datetime import timedelta
from typing import Dict, Any, List
from django.utils import timezone
from recruitment.models import Job, JobRequirement

logger = logging.getLogger(__name__)


class SkillMarketIntelligenceService:
    """
    Skill Market Intelligence Engine for HireNexa.
    Analyzes authorized platform job vacancies, skill combinations, and hiring trends.
    Provides verified metrics with full transparency regarding sample size and date ranges.
    """

    @classmethod
    def get_market_intelligence(cls, days: int = 90) -> Dict[str, Any]:
        """
        Analyzes authorized job requirements across active/recent jobs on HireNexa.
        Returns:
            - frequently_requested_skills
            - emerging_technology_skills
            - commonly_requested_qualifications
            - experience_requirements_breakdown
            - skill_combinations (co-occurrence)
            - metadata (data source, sample size, period, disclaimers)
        """
        cutoff_date = timezone.now() - timedelta(days=days)
        jobs_qs = Job.objects.filter(is_active=True, created_at__gte=cutoff_date)
        sample_size = jobs_qs.count()

        if sample_size == 0:
            # Fallback to all active jobs if recent range is sparse
            jobs_qs = Job.objects.filter(is_active=True)
            sample_size = jobs_qs.count()

        # 1. Frequently Requested Skills
        skill_counter = Counter()
        skill_pair_counter = Counter()
        qualification_counter = Counter()
        experience_dist = {
            "Entry Level (0-1 yr)": 0,
            "Mid Level (1-3 yrs)": 0,
            "Senior Level (3-6 yrs)": 0,
            "Lead / Principal (6+ yrs)": 0,
        }

        for job in jobs_qs:
            skills = job.skill_list()
            # Count individual skills
            for s in skills:
                clean = s.strip().title()
                if clean:
                    skill_counter[clean] += 1

            # Count skill co-occurrence pairs
            sorted_unique_skills = sorted(list(set(s.strip().title() for s in skills if s.strip())))
            for i in range(len(sorted_unique_skills)):
                for j in range(i + 1, len(sorted_unique_skills)):
                    pair = (sorted_unique_skills[i], sorted_unique_skills[j])
                    skill_pair_counter[pair] += 1

            # Qualification counts
            tc_display = job.get_target_course_display()
            qualification_counter[tc_display] += 1

            # Experience distribution
            exp_yrs = job.min_experience_years
            if exp_yrs <= 1:
                experience_dist["Entry Level (0-1 yr)"] += 1
            elif 1 < exp_yrs <= 3:
                experience_dist["Mid Level (1-3 yrs)"] += 1
            elif 3 < exp_yrs <= 6:
                experience_dist["Senior Level (3-6 yrs)"] += 1
            else:
                experience_dist["Lead / Principal (6+ yrs)"] += 1

        # Format Top Skills
        top_skills = []
        for skill_name, count in skill_counter.most_common(12):
            freq_pct = round((count / max(1, sample_size)) * 100, 1)
            top_skills.append({
                "skill": skill_name,
                "job_count": count,
                "percentage": freq_pct,
            })

        # Emerging Technology Skills (skills present in newest 30% of jobs)
        recent_jobs = list(jobs_qs.order_by("-created_at")[:max(1, int(sample_size * 0.3))])
        recent_skills = Counter()
        for j in recent_jobs:
            for s in j.skill_list():
                clean = s.strip().title()
                if clean:
                    recent_skills[clean] += 1

        emerging_skills = []
        for s_name, recent_count in recent_skills.most_common(8):
            total_count = skill_counter.get(s_name, 1)
            recency_share = round((recent_count / total_count) * 100, 1)
            emerging_skills.append({
                "skill": s_name,
                "recent_openings": recent_count,
                "momentum_score": recency_share,
            })

        # Skill Combinations / Tech Stacks
        skill_combinations = []
        for (s1, s2), count in skill_pair_counter.most_common(8):
            skill_combinations.append({
                "primary_skill": s1,
                "paired_skill": s2,
                "co_occurrence_count": count,
                "stack_pairing": f"{s1} + {s2}",
            })

        # Qualifications formatted
        qualifications = [
            {"qualification": k, "count": v, "percentage": round((v / max(1, sample_size)) * 100, 1)}
            for k, v in qualification_counter.most_common()
        ]

        # Experience breakdown formatted
        experience_breakdown = [
            {"tier": k, "count": v, "percentage": round((v / max(1, sample_size)) * 100, 1)}
            for k, v in experience_dist.items()
        ]

        metadata = {
            "data_source": "HireNexa Verified Platform Vacancies",
            "analysis_period": f"Past {days} days",
            "sample_size": sample_size,
            "last_updated": timezone.now().strftime("%B %d, %Y · %I:%M %p"),
            "statistical_disclaimer": (
                f"Metrics are calculated directly from {sample_size} active, authorized job postings "
                "on HireNexa. This report reflects hiring activity within our enterprise partner network "
                "and does not purport to represent universal global industry statistics."
            ),
        }

        return {
            "metadata": metadata,
            "frequently_requested_skills": top_skills,
            "emerging_technology_skills": emerging_skills,
            "commonly_requested_qualifications": qualifications,
            "experience_requirements": experience_breakdown,
            "skill_combinations": skill_combinations,
        }

# HireNexa AI Career Optimization (ACO) Ecosystem Specification

## Version 2.0 | Context-Aware | 8-Module Autonomous Career Copilot

---

## 1. Vision & Architecture Overview

The AI Career Optimization (ACO) Ecosystem connects student academic preparation, verified testing results, candidate portfolio artifacts, and real-time employer vacancy demand into an explainable, autonomous career copilot.

Unlike superficial resume rating widgets, every score in the ACO Suite has a mathematical calculation, and every recommendation is tied to live employer requirements from authorized platform jobs.

---

## 2. The 8 Intelligence Modules

```
                           ┌─────────────────────────────┐
                           │    CANDIDATE DATA ENGINE    │
                           │  (Profile, Tests, Portfolio)│
                           └──────────────┬──────────────┘
                                          │
    ┌──────────────────┬──────────────────┼──────────────────┬──────────────────┐
    ▼                  ▼                  ▼                  ▼                  ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  MODULE 1    │ │  MODULE 2    │ │  MODULE 3    │ │  MODULE 4    │ │  MODULE 5    │
│  Candidate   │ │  Skill Gap   │ │  Career      │ │  Resume ATS  │ │  Job Fit     │
│  Career      │ │  Analyzer    │ │  Roadmap     │ │  Optimization│ │  Intelligence│
│  Intelligence│ │              │ │  Generator   │ │  Intelligence│ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
    │                  │                  │                  │                  │
    └──────────────────┴──────────────────┼──────────────────┴──────────────────┘
                                          │
                       ┌──────────────────┴──────────────────┐
                       ▼                                     ▼
                ┌──────────────┐                      ┌──────────────┐
                │  MODULE 6    │                      │  MODULE 7    │
                │  Personalized│                      │  Interview   │
                │  4-Week Plan │                      │  Prep Engine │
                └──────┬───────┘                      └──────┬───────┘
                       │                                     │
                       └──────────────────┬──────────────────┘
                                          ▼
                                   ┌──────────────┐
                                   │  MODULE 8    │
                                   │  Career      │
                                   │  Analytics & │
                                   │  Readiness   │
                                   └──────────────┘
```

---

### Module 1: Candidate Career Intelligence
- **Responsibility**: Aggregates verified profile context: candidate full name, academic degree, university, target career role, CGPA, verified technical skills count, portfolio project count, and proctored examination attempts.
- **Service Method**: `CareerAssistantService.get_candidate_context(user)`
- **Key Outputs**:
  - `target_role`: Primary career objective (e.g. "Software Engineer", "Backend Developer").
  - `user_skills` & `resume_skills`: Normalized, deduplicated competencies.
  - `portfolio_projects`: Attached repository code and live demo links.
  - `recent_results`: Authenticated test scores and performance tier.

---

### Module 2: Skill Gap Analyzer
- **Responsibility**: Dynamically queries active, authorized job vacancies matching the candidate's target role, computes market frequency for each skill, and contrasts against the candidate's verified skills.
- **Service Method**: `CareerAssistantService.analyze_skill_gaps(user, target_role)`
- **Key Outputs**:
  - `present_skills`: Verified competencies matched in the candidate profile.
  - `missing_skills`: High-yield market competencies required by employers with percentage demand (`market_demand_pct`).
  - `reasoning`: Explainable text summarizing exact sample job count and highest-impact skills to acquire.

---

### Module 3: Career Roadmap Generator
- **Responsibility**: Produces a structured 8-step progression timeline linking fundamental computer science theory, relational database design, API engineering, testing, containerization, capstone projects, and placement rounds. Evaluates existing user skills and exam results to automatically mark steps as `COMPLETED`, `IN_PROGRESS`, or `UPCOMING`.
- **Service Method**: `CareerAssistantService.generate_career_roadmap(user)`
- **Key Outputs**:
  - 8 sequential milestones with estimated weeks, theoretical concepts, and practical criteria.
  - `overall_progress_pct`: Percentage of milestones completed.

---

### Module 4: Resume Optimization Intelligence
- **Responsibility**: Evaluates uploaded resumes for automated ATS (Applicant Tracking System) parseability, keyword coverage against target jobs, Google XYZ formula compliance ("Accomplished [X] as measured by [Y] by doing [Z]"), and recommended power action verbs.
- **Service Method**: `CareerAssistantService.generate_resume_improvements(user)`
- **Key Outputs**:
  - `ats_score`: Quantitative rating (0-100).
  - `ats_status`: Parseability tier ("Excellent", "Good", "Needs Optimization").
  - `action_verbs`: Curated technical action verbs (e.g., *Architected*, *Engineered*, *Optimized*).
  - Concrete category tips covering keyword saturation, quantifiable metrics, and verified skill credentials.

---

### Module 5: Job Fit Intelligence
- **Responsibility**: Ranks active platform job openings for the candidate using transparent multi-factor matching (skill overlap percentage, education target degree match, experience requirements).
- **Service Method**: `CareerAssistantService.recommend_jobs_with_reasoning(user)`
- **Key Outputs**:
  - `match_score`: Composite match percentage.
  - `matched_skills` vs `missing_skills`: Explicit itemized lists.
  - `reasoning`: Human-readable transparent explanation of why the position was recommended.

---

### Module 6: Personalized 4-Week Improvement Plan
- **Responsibility**: Generates an actionable 4-week learning sprint tailored specifically to the candidate's weakest examination topics and highest-yield missing market skills.
- **Service Method**: `CareerAssistantService.generate_improvement_plan(user)`
- **Sprint Schedule**:
  - *Week 1*: Foundation & Weak Spot Remediation (Theory review + practice tests).
  - *Week 2*: High-Demand Skill Acquisition (Practical exercises + code implementations).
  - *Week 3*: Portfolio Integration & Practical Proof (Repository + Project Portfolio upload).
  - *Week 4*: Placement Simulation & Interview Readiness (Mock CBT tests + STAR interview prep).

---

### Module 7: Interview Preparation Engine
- **Responsibility**: Curates authentic placement and technical interview questions from the verified question bank matching candidate's target role.
- **Service Method**: `CareerAssistantService.get_interview_practice(user)`
- **Key Outputs**:
  - Question statement, difficulty level, and subject.
  - Step-by-step solving logic and conceptual derivation.
  - Direct link to take timed practice tests.

---

### Module 8: Career Analytics & Placement Readiness
- **Responsibility**: Computes a single authoritative Placement Readiness Score (0-100) based on verified skills, portfolio code artifacts, completed test attempts, and average examination score.
- **Service Method**: `CareerAssistantService.track_career_development(user)`
- **Scoring Formula**:
  $$\text{Readiness Score} = \min\Big(100, (\text{Skills} \times 3) + (\text{Projects} \times 10) + (\text{Tests} \times 4) + (\text{Avg Score} \times 0.2)\Big)$$
- **Milestone Checklist**: Tracks core skill listing, resume upload, portfolio attachments, assessment passing, and overall placement threshold (≥ 70%).

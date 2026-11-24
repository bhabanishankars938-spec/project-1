# HireNexa Enterprise Examination Intelligence & CBT Engine Documentation

## Version 2.0 | Standard 16-Question Blueprint | Deterministic Scoring | Deduplicated Selection

---

## 1. Executive Summary & Core Architectural Principles

The HireNexa Examination Intelligence Engine powers student preparation across MCA entrance tracks (NIMCET MCA, OJEE MCA, CUET-PG SCQP09) and management tracks (CAT, MAT, CMAT). It provides a high-concurrency, server-authoritative Computer-Based Testing (CBT) interface.

### Core Principles
1. **Server-Authoritative Authority**: All scores, timers, attempts, and question selections reside and compute exclusively on the backend. Client-side state never dictates marks or attempt limits.
2. **Immutable Historical Records**: Attempts store permanent snapshots of marking rules, question counts, and marks (`total_possible_marks`, `positive_marks`, `negative_marks`). Historical attempts (e.g. 14-question exams) are never altered or retroactively corrupted.
3. **Deterministic Selection**: Every standard topic test dynamically selects exactly 16 unique questions strictly adhering to difficulty quotas without duplicating underlying concepts.

---

## 2. Standard Topic Examination Blueprint

| Parameter | Central Backend Configuration |
|---|---|
| **Question Count** | Exactly 16 questions per attempt |
| **Duration** | 21 minutes (1,260 seconds) |
| **Maximum Attempts** | Exactly 5 attempts per candidate per topic test |
| **Positive Marking** | +1.00 mark per correct answer |
| **Negative Marking** | -0.25 mark per incorrect answer |
| **Unanswered Marks** | 0.00 marks |
| **Total Possible Marks** | 16.00 marks |
| **Passing Score** | ≥ 40% (6.40 marks) |
| **Difficulty Distribution** | 5 Easy (31.25%), 7 Medium (43.75%), 4 Hard (25.00%) |

---

## 3. Intelligent Question Selection & Deduplication Architecture

Questions are selected via `select_topic_examination_questions(topic, user)` in `assessments/services.py`:

```
Candidate Requests Topic Test
       │
       ▼
Fetch Verified & Published Questions for Topic (status='VERIFIED' or 'PUBLISHED')
       │
       ▼
Partition by Difficulty: [Easy], [Medium], [Hard]
       │
       ▼
Analyze Candidate Historical Exposure
(Prioritize fresh questions never seen in previous attempts)
       │
       ▼
Apply Concept Diversity Algorithm:
  - Track seen `concept_identifier` set
  - For each difficulty tier, add question only if `concept_identifier` is new
  - If question bank permits, exactly 1 concept per question
       │
       ▼
Assemble Exact Tier Counts: 5 Easy + 7 Medium + 4 Hard = 16 Questions
       │
       ▼
Validate Invariants:
  - len(questions) == 16
  - len(set(question_ids)) == 16 (No duplicate question IDs)
  - All questions have verified correct option and explanation
       │
       ▼
Instantiate ExamAttempt & Link Questions
```

### Concept Fingerprinting
- Each question carries a canonical `concept_identifier` (e.g., `MATH_MATRIX_INVERSE`, `DBMS_BPLUS_TREE`).
- Selection prevents presenting two questions testing the same core formula or rule within one attempt.

---

## 4. Attempt Counter & Concurrent Attempt Policy

### Counter Policy
- Attempts are numbered sequentially: `Attempt 1 of 5`, `Attempt 2 of 5`, `Attempt 3 of 5`, `Attempt 4 of 5`, `Attempt 5 of 5`.
- Attempt counter increments at the point the attempt is officially created and started.
- After 5 attempts are completed or started, attempt creation is permanently locked:
  ```python
  if user_attempts.count() >= 5:
      raise ValidationError("You have reached the maximum limit of 5 attempts for this topic test.")
  ```

### Concurrent Attempt Prevention
- When a candidate requests to start a test, the engine queries for existing `IN_PROGRESS` attempts:
  ```python
  active_attempt = ExamAttempt.objects.filter(
      user=user,
      topic=topic,
      status=ExamAttempt.Status.IN_PROGRESS
  ).first()
  ```
- If an active attempt exists and its time has not expired, the user is redirected to resume that existing attempt rather than spawning a concurrent attempt.
- If expired, `finalize_submission(active_attempt, is_timeout=True)` is called atomically.

---

## 5. Server-Authoritative Scoring Engine

Scoring uses Python `Decimal` arithmetic for exact financial-grade precision without floating-point inaccuracies:

$$\text{Final Score} = (\text{Correct Count} \times 1.00) - (\text{Incorrect Count} \times 0.25)$$

$$\text{Score Percentage} = \frac{\max(0, \text{Final Score})}{\text{Total Possible Marks}} \times 100$$

### Performance Level Classification
- **Expert / Outstanding**: $\ge 85\%$
- **Advanced / Very Good**: $70\% - 84.9\%$
- **Intermediate / Competent**: $50\% - 69.9\%$
- **Novice / Needs Improvement**: $< 50\%$

---

## 6. Question Solution Intelligence

Post-submission, every question renders a multi-tiered pedagogical solution:
1. **Selected Answer vs Correct Answer**: Visual color coding (Green for correct, Red for chosen incorrect option, Slate for unanswered).
2. **Step-by-Step Explanation** (`explanation_text`): Complete derivation or proof.
3. **Short Solving Logic** (`solving_logic`): The 1-2 sentence core mental model.
4. **Important Concept Note** (`concept_note`): High-yield theoretical principle.
5. **Common Mistake Warning** (`common_mistake_warning`): Why distractors fail and how students get trapped.
6. **Exam Tip** (`exam_tip`): Shortcut formula or time-saving elimination technique.

---

## 7. Question Origin Separation Architecture

HireNexa strictly demarcates the genesis and pedagogical provenance of every question in the question bank. In `assessments/models.py`, `MCQQuestion` includes the `origin` field:

| Origin Key | Label | Badge Styling | Description |
|---|---|---|---|
| `AUTHENTIC_PYQ` | Authentic Previous Year Question | Purple (`badge-pyq`) | Real question from official historical papers (NIMCET, OJEE, CUET-PG) |
| `EXPERT_CURATED` | Expert Faculty Curated | Emerald (`badge-curated`) | Handcrafted by verified university faculty and domain experts |
| `AI_PRACTICE` | AI Generated Practice | Sky (`badge-practice`) | Generated by HireNexa AI for adaptive candidate skill training |

Candidates and faculty can filter questions and exams by origin, ensuring full transparency.

---

## 8. 5-Year Authentic PYQ Bank (2020–2024)

HireNexa includes a seeded bank of authentic previous year questions for:
- **NIMCET MCA (National Institute of Technology MCA Common Entrance Test)**: 2020, 2021, 2022, 2023, 2024
- **OJEE MCA (Odisha Joint Entrance Examination MCA)**: 2020, 2021, 2022, 2023, 2024
- **CUET-PG SCQP09 (Central Universities Entrance Test - MCA & Computer Science)**: 2022, 2023, 2024

Every PYQ includes:
- Verified source reference (e.g., `NIMCET-2024-Q12`, `OJEE-2023-Q45`)
- Complete mathematical or programmatic proof
- Why the correct option is uniquely valid
- Why the distractors are mathematically or logically invalid
- High-yield concept notes and exam shortcuts

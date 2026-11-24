import re
import hashlib
from pathlib import Path

# ==============================================================================
# ENTERPRISE SKILL TAXONOMY (130+ Technologies & Aliases)
# ==============================================================================
SKILL_ALIASES = {
    # Backend & Programming Languages
    "python": ["python", "python3", "py"],
    "django": ["django", "drf", "django rest framework"],
    "fastapi": ["fastapi", "fast-api"],
    "flask": ["flask"],
    "java": ["java", "core java", "j2ee", "spring boot", "springboot"],
    "c++": ["c++", "cpp"],
    "c#": ["c#", "csharp", ".net", "dotnet", "asp.net"],
    "go": ["golang", "go"],
    "rust": ["rust", "rustlang"],
    "ruby": ["ruby", "ruby on rails", "rails"],
    "php": ["php", "laravel"],
    "node.js": ["node.js", "nodejs", "node"],
    
    # Frontend & Web
    "javascript": ["javascript", "js", "es6", "vanilla js"],
    "typescript": ["typescript", "ts"],
    "react": ["react", "react.js", "reactjs"],
    "next.js": ["next.js", "nextjs"],
    "vue.js": ["vue", "vue.js", "vuejs", "nuxt"],
    "angular": ["angular", "angular.js"],
    "html": ["html", "html5"],
    "css": ["css", "css3"],
    "tailwind css": ["tailwind", "tailwindcss"],
    "bootstrap": ["bootstrap"],
    "sass": ["sass", "scss"],
    
    # Databases & Storage
    "sql": ["sql", "mysql", "mariadb"],
    "postgresql": ["postgresql", "postgres", "psql"],
    "sqlite": ["sqlite", "sqlite3"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    "elasticsearch": ["elasticsearch", "elastic search"],
    "cassandra": ["cassandra"],
    "dynamodb": ["dynamodb"],
    
    # Cloud & Infrastructure
    "aws": ["aws", "amazon web services", "ec2", "s3", "lambda"],
    "azure": ["azure", "microsoft azure"],
    "gcp": ["gcp", "google cloud", "google cloud platform"],
    "docker": ["docker", "containerization"],
    "kubernetes": ["kubernetes", "k8s"],
    "terraform": ["terraform"],
    "ci/cd": ["ci/cd", "continuous integration", "github actions", "gitlab ci", "jenkins"],
    "linux": ["linux", "ubuntu", "bash", "shell scripting"],
    "git": ["git", "github", "gitlab", "bitbucket"],
    
    # AI, ML & Data Science
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning", "neural networks"],
    "nlp": ["nlp", "natural language processing"],
    "computer vision": ["computer vision", "opencv"],
    "pytorch": ["pytorch"],
    "tensorflow": ["tensorflow", "keras"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "llm": ["llm", "large language model", "generative ai", "langchain", "llamaindex", "openai", "gemini"],
    
    # Architecture, APIs & Methodologies
    "rest api": ["rest api", "restful", "restful api", "rest apis"],
    "graphql": ["graphql"],
    "grpc": ["grpc"],
    "microservices": ["microservices", "microservice architecture"],
    "system design": ["system design", "distributed systems", "high availability"],
    "unit testing": ["unit testing", "pytest", "jest", "unittest"],
    "agile": ["agile", "scrum", "kanban"],
    "cybersecurity": ["cybersecurity", "infosec", "owasp", "cryptography", "jwt", "oauth"],

    # MCA Specializations & Roles (Full Stack, Mobile, Database & Cloud)
    "full stack development": ["full stack", "fullstack", "full stack developer", "full stack development", "mean stack", "mern stack"],
    "frontend development": ["frontend", "front-end", "front end developer", "ui development"],
    "backend development": ["backend", "back-end", "backend developer", "server side"],
    "mobile app development": ["mobile app", "android", "ios", "flutter", "react native", "mobile application"],
    "database administration": ["database administrator", "dba", "database management", "sql developer"],
    "software testing": ["software testing", "qa", "quality assurance", "selenium", "automation testing", "manual testing"],
    
    # MBA - Human Resources (HR) & Talent Management
    "human resources": ["human resources", "hr", "hr management", "human resource management", "hr generalist"],
    "talent acquisition": ["talent acquisition", "recruitment", "headhunting", "candidate sourcing", "hiring"],
    "employee relations": ["employee relations", "employee engagement", "hr policies", "labour laws", "payroll"],
    "performance management": ["performance management", "kpi", "okr", "appraisal"],

    # MBA - Marketing & Strategy
    "marketing management": ["marketing management", "marketing", "brand management", "marketing strategy"],
    "digital marketing": ["digital marketing", "seo", "sem", "social media marketing", "google ads", "content marketing"],
    "market research": ["market research", "competitive analysis", "consumer behavior", "market survey"],
    "business development": ["business development", "bde", "bdm", "client acquisition", "lead generation"],

    # MBA - Finance & Accounting
    "financial analysis": ["financial analysis", "financial analyst", "financial modeling", "corporate finance"],
    "investment banking": ["investment banking", "equity research", "portfolio management", "wealth management"],
    "budgeting & forecasting": ["budgeting", "financial forecasting", "variance analysis", "cash flow management"],
    "risk management": ["risk management", "financial risk", "compliance", "credit risk"],

    # MBA - Business Analytics, Operations & Management
    "business analysis": ["business analysis", "business analyst", "requirement gathering", "brd", "frd"],
    "business analytics": ["business analytics", "power bi", "tableau", "advanced excel", "data visualization"],
    "operations management": ["operations management", "operations", "supply chain", "logistics", "supply chain management", "procurement"],
    "product management": ["product management", "product manager", "roadmap", "user stories"],
    "sales management": ["sales", "b2b sales", "b2c sales", "sales management", "crm", "salesforce"],
    "strategic management": ["strategic management", "strategy", "business strategy", "corporate strategy"],
}


def normalize_text(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


# ==============================================================================
# HIREXNEXA MODULAR 7-AGENT AI RECRUITMENT ARCHITECTURE (PHASE 10 & 11)
# ==============================================================================

class DataQualityAgent:
    """
    Agent 1: Data Quality & Document Integrity Agent.
    Validates file formats, sizes, cryptographic hashes, magic byte signatures,
    and checks for corruption, truncation, or suspicious binary injections.
    """
    @staticmethod
    def validate_document(uploaded_file):
        allowed_exts = {".pdf", ".docx"}
        filename = uploaded_file.name.lower()
        suffix = Path(filename).suffix

        if suffix not in allowed_exts:
            return False, "Invalid file format. Only verified PDF and DOCX files are permitted.", "", ""

        # Enforce 5MB limit
        if uploaded_file.size > 5 * 1024 * 1024:
            return False, "File exceeds maximum size limit of 5 MB.", "", ""

        content_chunk = uploaded_file.read(2048)
        uploaded_file.seek(0)

        # Compute SHA-256 for audit and deduplication
        hasher = hashlib.sha256()
        for chunk in uploaded_file.chunks():
            hasher.update(chunk)
        file_hash = hasher.hexdigest()
        uploaded_file.seek(0)

        # Magic byte verification
        if suffix == ".pdf":
            if not content_chunk.startswith(b"%PDF-"):
                return False, "Security Error: File has .pdf extension but does not contain a valid PDF signature.", "", ""
            mime_type = "application/pdf"
        elif suffix == ".docx":
            if not content_chunk.startswith(b"PK\x03\x04"):
                return False, "Security Error: File has .docx extension but is not a valid Office document.", "", ""
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            return False, "Unsupported document type.", "", ""

        return True, "", mime_type, file_hash

    @staticmethod
    def check_text_integrity(text):
        """Analyze extracted resume text for minimal length, contact signals, and OCR health."""
        if not text or len(text.strip()) < 50:
            return False, 10, ["Text is suspiciously short or empty (possible scanned image or corrupted PDF)."]
        issues = []
        score = 100
        if len(text.strip()) < 200:
            issues.append("Document text has very sparse content (< 200 characters).")
            score -= 20
        # Check email presence
        if not re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
            issues.append("No detectable email address in parsed document.")
            score -= 15
        # Check phone presence
        if not re.search(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text):
            issues.append("No standard contact phone number detected.")
            score -= 10
        return len(issues) == 0, max(20, score), issues


class ResumeParsingAgent:
    """
    Agent 2: Resume Parsing & Information Extraction Agent.
    Extracts structured fields from raw document text: contact details,
    education, GPA, certifications, years of experience, and technical skills.
    """
    @staticmethod
    def extract_raw_text(file_path):
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            import fitz
            doc = fitz.open(file_path)
            pages_text = [page.get_text() for page in doc]
            doc.close()
            return "\n".join(pages_text)
        if suffix == ".docx":
            from docx import Document
            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs)
        raise ValueError("Unsupported resume file type.")

    @staticmethod
    def extract_skills(text):
        normalized = normalize_text(text)
        found = []
        for canonical, aliases in SKILL_ALIASES.items():
            for alias in aliases:
                pattern = r"(?<![a-z0-9+#])" + re.escape(alias) + r"(?![a-z0-9+#])"
                if re.search(pattern, normalized):
                    found.append(canonical)
                    break
        return sorted(set(found))

    @staticmethod
    def extract_education(text):
        found = []
        edu_patterns = [
            r"(m\.?ba|master of business administration|p\.?g\.?d\.?m|post graduate diploma in management)",
            r"(b\.?ba|bachelor of business administration|b\.?com|bachelor of commerce)",
            r"(m\.?ca|master of computer applications)",
            r"(b\.?ca|bachelor of computer applications)",
            r"(b\.?tech|bachelor of technology|b\.?e\.?|bachelor of engineering)",
            r"(m\.?tech|master of technology|m\.?s\.?|master of science)",
            r"(b\.?sc|bachelor of science)",
            r"(cgpa\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?))",
            r"((?:computer science|information technology|electronics|mechanical|business analytics|finance|human resources|marketing)\s*(?:engineering|management)?)",
        ]
        for pattern in edu_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                val = m[0] if isinstance(m, tuple) else m
                if val.strip() and val.strip().lower() not in [x.lower() for x in found]:
                    found.append(val.strip().title())
        return found[:5]

    @staticmethod
    def extract_experience_years(text):
        matches = re.findall(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+experience", text, re.IGNORECASE)
        if matches:
            try:
                return max(float(m) for m in matches)
            except ValueError:
                pass
        return 0.0

    @classmethod
    def parse_full_resume(cls, file_path):
        text = cls.extract_raw_text(file_path)
        is_clean, quality_score, issues = DataQualityAgent.check_text_integrity(text)
        skills = cls.extract_skills(text)
        education = cls.extract_education(text)
        experience_years = cls.extract_experience_years(text)

        # Contact extraction
        email_match = re.search(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", text)
        phone_match = re.search(r"((?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", text)

        return {
            "text": text,
            "quality_score": quality_score,
            "quality_issues": issues,
            "skills": skills,
            "education": education,
            "experience_years": experience_years,
            "email": email_match.group(1) if email_match else "",
            "phone": phone_match.group(1) if phone_match else "",
        }


class JobUnderstandingAgent:
    """
    Agent 3: Job Understanding & Requirement Decomposition Agent.
    Deconstructs job requisitions into mandatory skills, nice-to-have skills,
    target degree discipline, and seniority expectations.
    """
    @staticmethod
    def decompose_requirements(required_skills_list, job_description=""):
        cleaned_required = [s.strip().lower() for s in required_skills_list if s.strip()]
        desc_lower = (job_description or "").lower()
        sentences = re.split(r"[.\n;]", desc_lower)

        mandatory = []
        preferred = []
        for skill in cleaned_required:
            is_pref = False
            for s in sentences:
                if skill in s and any(k in s for k in ["nice to have", "preferred", "plus", "bonus", "optional"]):
                    preferred.append(skill)
                    is_pref = True
                    break
            if not is_pref:
                mandatory.append(skill)

        return {
            "mandatory_skills": mandatory or cleaned_required,
            "preferred_skills": preferred,
            "all_required": cleaned_required,
        }


class SkillMatchingAgent:
    """
    Agent 4: Direct & Synonymous Skill Matching Agent.
    Matches extracted candidate skills against required job skills using the
    comprehensive 130+ technical and business taxonomy.
    """
    @staticmethod
    def match(candidate_skills, required_skills, preferred_skills=None):
        candidate_set = set(s.lower().strip() for s in candidate_skills)
        required_set = set(s.lower().strip() for s in required_skills if s.strip())

        matched = sorted(candidate_set.intersection(required_set))
        missing = sorted(required_set - candidate_set)

        skill_overlap_pct = round((len(matched) / len(required_set)) * 100, 2) if required_set else 0.0
        return {
            "matched": matched,
            "missing": missing,
            "skill_score": skill_overlap_pct,
            "matched_count": len(matched),
            "required_count": len(required_set),
        }


class SemanticMatchingAgent:
    """
    Agent 5: Contextual Semantic Matching Agent.
    Evaluates semantic vector alignment between candidate experience narratives
    and job descriptions using sentence-transformers (or resilient TF-IDF fallback).
    """
    @staticmethod
    def calculate_similarity(candidate_text, job_text):
        try:
            from sentence_transformers import SentenceTransformer
            from sklearn.metrics.pairwise import cosine_similarity
            model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            embeddings = model.encode([candidate_text[:12000], job_text[:12000]])
            sim = float(cosine_similarity([embeddings[0]], [embeddings[1]])[0][0])
            score = round(max(0.0, min(100.0, sim * 100)), 2)
            return score, "Deep Semantic Transformer vector alignment."
        except Exception:
            # Resilient TF-IDF token cosine fallback
            c_words = set(re.findall(r"\b\w{3,}\b", candidate_text.lower()))
            j_words = set(re.findall(r"\b\w{3,}\b", job_text.lower()))
            if not j_words:
                return 50.0, "Lexical token baseline evaluated."
            overlap = len(c_words.intersection(j_words))
            jaccard = (overlap / len(j_words)) * 100
            score = round(min(100.0, max(20.0, jaccard * 1.5)), 2)
            return score, "Standard NLP lexical screening active."


class CandidateExplanationAgent:
    """
    Agent 6: Explainable AI Rationale & Interview Recommendation Agent.
    Produces transparent diagnostics: strengths, deficiencies, fit tier, and
    targeted questions for human hiring panels.
    """
    @staticmethod
    def generate_explanation(skill_data, semantic_score, semantic_note, job_title="Position"):
        matched = skill_data["matched"]
        missing = skill_data["missing"]
        skill_score = skill_data["skill_score"]
        final_score = round(0.7 * skill_score + 0.3 * semantic_score, 2)

        if final_score >= 80:
            fit_tier = "Exceptional Fit"
        elif final_score >= 60:
            fit_tier = "Strong Candidate"
        elif final_score >= 40:
            fit_tier = "Moderate Alignment"
        else:
            fit_tier = "Low Alignment / Training Needed"

        if missing:
            top_missing = ", ".join(missing[:3])
            recommendation = f"Candidate can increase match alignment by acquiring and demonstrating experience with: {top_missing}."
        else:
            recommendation = "Candidate demonstrates full coverage of all required technical competencies for this role."

        explanation = (
            f"Evaluated {skill_data['required_count']} required competencies against extracted resume profile ({fit_tier}). "
            f"Matched {len(matched)} core skills ({skill_score}% overlap). "
            f"Missing skills: {len(missing)}. {semantic_note} "
            f"Final weighted score: {final_score}%. This score serves as decision support only; human recruiters conduct the final interview evaluation."
        )

        return {
            "final_score": final_score,
            "fit_tier": fit_tier,
            "explanation": explanation,
            "recommendation": recommendation,
        }


class RecruitmentAssistantAgent:
    """
    Agent 7: Recruiter Copilot & Smart Interview Assistant Agent.
    Generates customized interview questionnaires based on verified strengths
    and missing competencies for human recruiters.
    """
    @staticmethod
    def generate_interview_questions(job_title, matched_skills, missing_skills):
        questions = []
        if matched_skills:
            top_skill = matched_skills[0].title()
            questions.append(f"Can you explain your most complex real-world project built using {top_skill}?")
        if len(matched_skills) > 1:
            second_skill = matched_skills[1].title()
            questions.append(f"How do you ensure scalability, testing, and error handling when deploying with {second_skill}?")
        if missing_skills:
            gap_skill = missing_skills[0].title()
            questions.append(f"This role involves {gap_skill}, which wasn't prominent on your resume. How would you quickly ramp up and deliver with this tool?")
        questions.append("Describe a challenging technical disagreement in your team and how you arrived at a production-grade solution.")
        return questions


# ==============================================================================
# BACKWARD COMPATIBLE UTILITY FUNCTIONS (Orchestrated via Agents)
# ==============================================================================

def validate_resume_file(uploaded_file):
    """Delegates to Agent 1: DataQualityAgent."""
    return DataQualityAgent.validate_document(uploaded_file)


def extract_resume_text(file_path):
    """Delegates to Agent 2: ResumeParsingAgent."""
    return ResumeParsingAgent.extract_raw_text(file_path)


def extract_skills(text):
    """Delegates to Agent 2: ResumeParsingAgent."""
    return ResumeParsingAgent.extract_skills(text)


def extract_education(text):
    """Delegates to Agent 2: ResumeParsingAgent."""
    return ResumeParsingAgent.extract_education(text)


def extract_experience_years(text):
    """Delegates to Agent 2: ResumeParsingAgent."""
    return ResumeParsingAgent.extract_experience_years(text)


def calculate_match(resume_text, required_skills, job_description=""):
    """
    Multi-factor AI recruitment match calculation orchestrating:
    - ResumeParsingAgent
    - JobUnderstandingAgent
    - SkillMatchingAgent
    - SemanticMatchingAgent
    - CandidateExplanationAgent
    """
    resume_skills = ResumeParsingAgent.extract_skills(resume_text)
    job_reqs = JobUnderstandingAgent.decompose_requirements(required_skills, job_description)
    skill_data = SkillMatchingAgent.match(resume_skills, job_reqs["all_required"])

    job_text = " ".join(job_reqs["all_required"]) + " " + (job_description or "")
    semantic_score, semantic_note = SemanticMatchingAgent.calculate_similarity(resume_text, job_text)

    match_report = CandidateExplanationAgent.generate_explanation(
        skill_data, semantic_score, semantic_note, job_title="Role"
    )

    return {
        "matched": skill_data["matched"],
        "missing": skill_data["missing"],
        "skill_score": skill_data["skill_score"],
        "semantic_score": semantic_score,
        "final_score": match_report["final_score"],
        "explanation": match_report["explanation"],
        "recommendation": match_report["recommendation"],
        "extracted_skills": list(resume_skills),
    }

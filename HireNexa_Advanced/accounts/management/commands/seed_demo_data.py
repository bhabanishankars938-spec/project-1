import os
import secrets
import string
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from accounts.models import User, AuditLog
from accounts.services.rate_limiter import RateLimiter
from recruitment.models import (
    Organization, OrganizationMember, Subscription, SubscriptionPlan,
    RecruiterProfile, CandidateProfile, CandidateEducation, CandidateSkill, CandidateProject,
    FreelancerProfile, Resume, Job, JobRequirement, Application, Project, ProjectProposal
)


class Command(BaseCommand):
    help = "Seed realistic sample demo data across all platform roles (Development DEBUG only)"

    def handle(self, *args, **options):
        # 1. Enforce development-only safety barrier
        if not getattr(settings, "DEBUG", False):
            raise CommandError("Security Violation: seed_demo_data can only be executed in development mode (DEBUG=True).")

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== HIRENEXA ENTERPRISE DEMO DATA SEEDING ==="))

        # 2. Determine Test User Password
        raw_password = (os.environ.get("TEST_USER_PASSWORD") or "").strip()
        generated_password = False
        if not raw_password:
            alphabet = string.ascii_letters + string.digits + "!@#$%"
            raw_password = "".join(secrets.choice(alphabet) for _ in range(14)) + "1aA!"
            generated_password = True

        now = timezone.now()

        # Helper to create or update active verified user
        def get_or_create_user(username, email, phone, role, first_name="", last_name=""):
            email_clean = email.lower().strip()
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email_clean,
                    "phone_number": phone,
                    "role": role,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,
                    "is_email_verified": True,
                    "is_phone_verified": True,
                    "email_verified_at": now,
                    "phone_verified_at": now,
                }
            )
            user.email = email_clean
            user.phone_number = phone
            user.role = role
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = True
            user.is_email_verified = True
            user.is_phone_verified = True
            user.email_verified_at = now
            user.phone_verified_at = now
            user.set_password(raw_password)
            user.save()
            return user, created

        # 3. Create Company Admin & Organization
        company_admin, _ = get_or_create_user(
            username="acme_admin",
            email="admin@acmetech.com",
            phone="+919800000001",
            role=User.Role.COMPANY_ADMIN,
            first_name="Rajesh",
            last_name="Mehta"
        )

        org, _ = Organization.objects.get_or_create(
            name="Acme Technologies",
            defaults={
                "slug": "acme-technologies",
                "description": "Global enterprise cloud software, AI automation, and distributed systems engineering.",
                "website": "https://acmetech.example.com",
                "industry": "Enterprise Cloud & AI Solutions",
                "company_size": "250-500 employees",
                "location": "Bangalore, India",
                "verification_status": Organization.VerificationStatus.APPROVED,
                "is_active": True,
            }
        )

        OrganizationMember.objects.update_or_create(
            organization=org,
            user=company_admin,
            defaults={
                "role": OrganizationMember.MemberRole.ADMIN,
                "department": "Executive Leadership",
                "can_post_jobs": True,
                "can_schedule_interviews": True,
                "can_download_resumes": True,
                "is_active": True,
            }
        )

        Subscription.objects.update_or_create(
            organization=org,
            defaults={
                "plan_name": Subscription.Plan.ENTERPRISE,
                "status": Subscription.Status.ACTIVE,
                "max_active_jobs": 50,
                "max_hr_seats": 10,
                "ai_credits_monthly": 5000,
            }
        )

        # 4. Create 2 HR / Recruiters linked to Acme Technologies
        hr1, _ = get_or_create_user(
            username="priya_recruiter",
            email="priya@acmetech.com",
            phone="+919800000002",
            role=User.Role.RECRUITER,
            first_name="Priya",
            last_name="Sharma"
        )
        RecruiterProfile.objects.update_or_create(
            user=hr1,
            defaults={"company_name": "Acme Technologies"}
        )
        OrganizationMember.objects.update_or_create(
            organization=org,
            user=hr1,
            defaults={
                "role": OrganizationMember.MemberRole.HR,
                "department": "Engineering Talent Acquisition",
                "can_post_jobs": True,
                "can_schedule_interviews": True,
                "can_download_resumes": True,
                "is_active": True,
            }
        )

        hr2, _ = get_or_create_user(
            username="rahul_hr",
            email="rahul@acmetech.com",
            phone="+919800000003",
            role=User.Role.RECRUITER,
            first_name="Rahul",
            last_name="Verma"
        )
        RecruiterProfile.objects.update_or_create(
            user=hr2,
            defaults={"company_name": "Acme Technologies"}
        )
        OrganizationMember.objects.update_or_create(
            organization=org,
            user=hr2,
            defaults={
                "role": OrganizationMember.MemberRole.HR,
                "department": "Technical Hiring",
                "can_post_jobs": True,
                "can_schedule_interviews": True,
                "can_download_resumes": True,
                "is_active": True,
            }
        )

        # 5. Create 3 Students / Candidates
        cand1, _ = get_or_create_user(
            username="aarav_student",
            email="aarav@college.edu",
            phone="+919800000004",
            role=User.Role.CANDIDATE,
            first_name="Aarav",
            last_name="Patel"
        )
        CandidateProfile.objects.update_or_create(
            user=cand1,
            defaults={
                "full_name": "Aarav Patel",
                "headline": "Aspiring Full-Stack Software Engineer | MCA 2025",
                "phone": "+919800000004",
                "education": "Master of Computer Applications (MCA)",
                "university": "Delhi Technological University",
                "graduation_year": 2025,
                "cgpa": 8.9,
                "location": "New Delhi, India",
                "skills": "Python, Django, React, PostgreSQL, Docker, Git",
                "github_url": "https://github.com/aarav-patel",
                "linkedin_url": "https://linkedin.com/in/aarav-patel",
                "bio": "Passionate software engineer building resilient backend services and modern reactive web applications.",
                "resume_consent": True,
            }
        )

        cand2, _ = get_or_create_user(
            username="riya_candidate",
            email="riya@university.edu",
            phone="+919800000005",
            role=User.Role.CANDIDATE,
            first_name="Riya",
            last_name="Sen"
        )
        CandidateProfile.objects.update_or_create(
            user=cand2,
            defaults={
                "full_name": "Riya Sen",
                "headline": "Machine Learning Engineer & Data Scientist | B.Tech CSE",
                "phone": "+919800000005",
                "education": "B.Tech Computer Science & Engineering",
                "university": "IIT Bombay",
                "graduation_year": 2024,
                "cgpa": 9.2,
                "location": "Mumbai, India",
                "skills": "Python, PyTorch, Transformers, LangChain, FastAPI, Redis",
                "github_url": "https://github.com/riya-sen",
                "linkedin_url": "https://linkedin.com/in/riya-sen",
                "bio": "Specialized in large language model fine-tuning, RAG architectures, and scalable inference APIs.",
                "resume_consent": True,
            }
        )

        cand3, _ = get_or_create_user(
            username="aditya_dev",
            email="aditya@institute.edu",
            phone="+919800000006",
            role=User.Role.CANDIDATE,
            first_name="Aditya",
            last_name="Kapoor"
        )
        CandidateProfile.objects.update_or_create(
            user=cand3,
            defaults={
                "full_name": "Aditya Kapoor",
                "headline": "Cloud DevOps & Backend Specialist | MCA Graduate",
                "phone": "+919800000006",
                "education": "Master of Computer Applications (MCA)",
                "university": "NIT Trichy",
                "graduation_year": 2024,
                "cgpa": 8.6,
                "location": "Bangalore, India",
                "skills": "Go, Kubernetes, AWS, Terraform, CI/CD, Linux, Python",
                "github_url": "https://github.com/aditya-dev",
                "linkedin_url": "https://linkedin.com/in/aditya-kapoor",
                "bio": "Building reliable cloud-native infrastructure, automated deployment pipelines, and microservices.",
                "resume_consent": True,
            }
        )

        # 6. Create 2 Freelancers
        free1, _ = get_or_create_user(
            username="vikram_freelance",
            email="vikram@freelance.dev",
            phone="+919800000007",
            role=User.Role.FREELANCER,
            first_name="Vikram",
            last_name="Singh"
        )
        FreelancerProfile.objects.update_or_create(
            user=free1,
            defaults={
                "full_name": "Vikram Singh",
                "headline": "Principal Full-Stack Contractor | 7+ Years Experience",
                "hourly_rate": 65.00,
                "experience_years": 7,
                "skills": "Django, FastAPI, React, Next.js, PostgreSQL, AWS Architecture",
                "portfolio_url": "https://vikram-contractor.example.com",
                "github_url": "https://github.com/vikram-contractor",
                "linkedin_url": "https://linkedin.com/in/vikram-singh",
                "bio": "Expert contractor helping startups ship MVP to Enterprise Grade architectures with zero downtime.",
                "availability": "AVAILABLE",
            }
        )

        free2, _ = get_or_create_user(
            username="ananya_contractor",
            email="ananya@codecraft.io",
            phone="+919800000008",
            role=User.Role.FREELANCER,
            first_name="Ananya",
            last_name="Roy"
        )
        FreelancerProfile.objects.update_or_create(
            user=free2,
            defaults={
                "full_name": "Ananya Roy",
                "headline": "Senior UI/UX & Frontend Specialist | React & Vue",
                "hourly_rate": 55.00,
                "experience_years": 5,
                "skills": "React, TypeScript, TailwindCSS, Figma, GraphQL, UI Performance",
                "portfolio_url": "https://ananya-designs.example.com",
                "github_url": "https://github.com/ananya-roy",
                "linkedin_url": "https://linkedin.com/in/ananya-roy",
                "bio": "Crafting accessible, pixel-perfect user experiences and performant design system component libraries.",
                "availability": "AVAILABLE",
            }
        )

        # 7. Create Exactly 11 Active Job Postings (Matching Navbar "Find Jobs 11")
        jobs_data = [
            ("Senior Full-Stack Python/Django Engineer", "Engineering", "MCA", 3, "FULL_TIME", "EXPERIENCED", 1800000, 2600000, "Bangalore, India", "HYBRID", "Python, Django, PostgreSQL, Celery, Redis, Docker"),
            ("Cloud DevOps & Kubernetes Architect", "Infrastructure", "ANY", 2, "FULL_TIME", "SENIOR", 2200000, 3200000, "Remote - India", "REMOTE", "Kubernetes, AWS, Terraform, Helm, CI/CD, Linux"),
            ("AI/ML Research Engineer (LLM Specialization)", "AI Labs", "ANY", 2, "FULL_TIME", "EXPERIENCED", 2400000, 3500000, "Bangalore, India", "ONSITE", "PyTorch, Transformers, LangChain, RAG, Python, CUDA"),
            ("Frontend Engineer - React & Next.js", "Engineering", "ANY", 3, "FULL_TIME", "MID", 1200000, 1800000, "Hyderabad, India", "HYBRID", "React, TypeScript, Next.js, TailwindCSS, REST APIs"),
            ("Backend Systems Engineer - Distributed Systems", "Platform", "MCA", 2, "FULL_TIME", "SENIOR", 2000000, 2800000, "Pune, India", "HYBRID", "Go, Python, Kafka, gRPC, Distributed Systems, PostgreSQL"),
            ("Data Platform & Analytics Engineer", "Data", "ANY", 2, "FULL_TIME", "MID", 1400000, 2000000, "Bangalore, India", "ONSITE", "Python, Apache Spark, Snowflake, SQL, Airflow, dbt"),
            ("Mobile App Developer - Flutter & Kotlin", "Mobile", "ANY", 2, "FULL_TIME", "MID", 1100000, 1600000, "Chennai, India", "HYBRID", "Flutter, Dart, Kotlin, Mobile Architecture, Clean Code"),
            ("Security Operations & DevSecOps Specialist", "Security", "ANY", 1, "FULL_TIME", "SENIOR", 2200000, 3000000, "Bangalore, India", "ONSITE", "OWASP, SAST/DAST, Cloud Security, SIEM, SOC, Python"),
            ("Technical Product Manager - Enterprise SaaS", "Product", "MBA", 1, "FULL_TIME", "SENIOR", 2500000, 3600000, "Gurgaon, India", "HYBRID", "Product Roadmap, Agile, User Stories, API Specs, SQL"),
            ("QA Automation & Performance Testing Engineer", "Quality", "ANY", 2, "FULL_TIME", "MID", 900000, 1400000, "Noida, India", "HYBRID", "Selenium, Playwright, PyTest, JMeter, CI/CD, Python"),
            ("Site Reliability Engineer (SRE)", "Infrastructure", "ANY", 2, "FULL_TIME", "MID", 1600000, 2300000, "Bangalore, India", "REMOTE", "Prometheus, Grafana, Linux, Docker, Python, Reliability Engineering"),
        ]

        created_jobs = []
        for idx, (title, dept, course, vac, j_type, exp_lvl, s_min, s_max, loc, wp_type, skills) in enumerate(jobs_data, 1):
            job, _ = Job.objects.update_or_create(
                organization=org,
                title=title,
                defaults={
                    "recruiter": hr1 if idx % 2 != 0 else hr2,
                    "company_name": org.name,
                    "department": dept,
                    "target_course": course,
                    "vacancies": vac,
                    "job_type": j_type,
                    "experience_level": exp_lvl,
                    "salary_currency": "INR",
                    "salary_period": "YEAR",
                    "salary_min": s_min,
                    "salary_max": s_max,
                    "is_salary_negotiable": True,
                    "display_salary_publicly": True,
                    "location": loc,
                    "workplace_type": wp_type,
                    "description": f"We are seeking an outstanding {title} to scale our high-throughput enterprise platforms. You will work alongside world-class engineers driving core product initiatives.",
                    "required_skills": skills,
                    "min_experience_years": 2 if exp_lvl == "MID" else (4 if exp_lvl in ("EXPERIENCED", "SENIOR") else 1),
                    "status": "ACTIVE",
                    "is_featured": (idx <= 3),
                    "is_active": True,
                    "deadline": now + timezone.timedelta(days=45),
                }
            )
            created_jobs.append(job)

        # 8. Create Sample Resumes and Applications for Candidates
        resume1, _ = Resume.objects.update_or_create(
            candidate=cand1,
            file_name="aarav_patel_resume.pdf",
            defaults={
                "file": ContentFile(b"%PDF-1.4 sample resume for Aarav Patel", name="aarav_patel_resume.pdf"),
                "file_size": 2048,
                "mime_type": "application/pdf",
                "extracted_text": "Aarav Patel Full Stack Python Django React PostgreSQL Docker",
                "is_verified": True,
            }
        )

        resume2, _ = Resume.objects.update_or_create(
            candidate=cand2,
            file_name="riya_sen_resume.pdf",
            defaults={
                "file": ContentFile(b"%PDF-1.4 sample resume for Riya Sen", name="riya_sen_resume.pdf"),
                "file_size": 2560,
                "mime_type": "application/pdf",
                "extracted_text": "Riya Sen Machine Learning Engineer PyTorch Transformers LangChain FastAPI",
                "is_verified": True,
            }
        )

        resume3, _ = Resume.objects.update_or_create(
            candidate=cand3,
            file_name="aditya_kapoor_resume.pdf",
            defaults={
                "file": ContentFile(b"%PDF-1.4 sample resume for Aditya Kapoor", name="aditya_kapoor_resume.pdf"),
                "file_size": 1920,
                "mime_type": "application/pdf",
                "extracted_text": "Aditya Kapoor Cloud DevOps SRE Kubernetes AWS Terraform Go",
                "is_verified": True,
            }
        )

        if len(created_jobs) >= 3:
            Application.objects.update_or_create(
                candidate=cand1,
                job=created_jobs[0],
                defaults={
                    "resume": resume1,
                    "status": "UNDER_REVIEW",
                    "skill_score": 92.5,
                    "semantic_score": 88.0,
                    "final_score": 90.25,
                    "explanation": "High coverage of Python, Django, PostgreSQL, and Docker skill competencies.",
                }
            )
            Application.objects.update_or_create(
                candidate=cand2,
                job=created_jobs[2],
                defaults={
                    "resume": resume2,
                    "status": "INTERVIEW_SCHEDULED",
                    "skill_score": 96.0,
                    "semantic_score": 94.5,
                    "final_score": 95.25,
                    "explanation": "Exceptional alignment with PyTorch, Transformers, RAG architectures, and LLM fine-tuning.",
                }
            )
            Application.objects.update_or_create(
                candidate=cand3,
                job=created_jobs[1],
                defaults={
                    "resume": resume3,
                    "status": "APPLIED",
                    "skill_score": 86.0,
                    "semantic_score": 84.0,
                    "final_score": 85.0,
                    "explanation": "Solid foundation in Kubernetes, Terraform, and cloud infrastructure.",
                }
            )

        # 9. Create Sample Freelance Gigs & Proposals
        proj1, _ = Project.objects.update_or_create(
            title="FastAPI Microservices Optimization & Async Migration",
            defaults={
                "client": company_admin,
                "company_name": "Acme Technologies",
                "description": "Refactor existing synchronous services to async FastAPI endpoints with Redis caching and connection pooling.",
                "budget_type": "FIXED",
                "budget_min": 75000,
                "budget_max": 120000,
                "required_skills": "Python, FastAPI, AsyncIO, Redis, Docker",
                "duration": "4 weeks",
                "is_active": True,
            }
        )
        proj2, _ = Project.objects.update_or_create(
            title="Design System Component Library (React & Tailwind)",
            defaults={
                "client": hr1,
                "company_name": "Acme Technologies",
                "description": "Develop 30+ accessible WCAG AA compliant interactive components in React, TypeScript and TailwindCSS.",
                "budget_type": "HOURLY",
                "budget_min": 3500,
                "budget_max": 5000,
                "required_skills": "React, TypeScript, TailwindCSS, Storybook, Figma",
                "duration": "6 weeks",
                "is_active": True,
            }
        )

        ProjectProposal.objects.update_or_create(
            project=proj1,
            freelancer=free1,
            defaults={
                "cover_letter": "I have completed 10+ async microservice refactoring projects. Can deliver high throughput with test benchmarks.",
                "bid_amount": 95000,
                "estimated_days": 21,
                "status": "PENDING",
            }
        )
        ProjectProposal.objects.update_or_create(
            project=proj2,
            freelancer=free2,
            defaults={
                "cover_letter": "Specialist in accessible component libraries with Storybook and automated visual regression testing.",
                "bid_amount": 4200,
                "estimated_days": 30,
                "status": "ACCEPTED",
            }
        )

        # 10. Clear Rate Limiter and Caches to ensure immediate sign-in capability
        RateLimiter.reset_all()
        from django.core.cache import cache
        cache.clear()

        # Audit log of seeding
        AuditLog.objects.create(
            action="DEMO_DATA_SEEDED",
            ip_address="127.0.0.1",
            details={
                "company_admin": company_admin.username,
                "recruiters_count": 2,
                "candidates_count": 3,
                "freelancers_count": 2,
                "jobs_count": len(created_jobs),
            }
        )

        self.stdout.write(self.style.SUCCESS(f"✓ Company Admin created: '{company_admin.username}' ({company_admin.email})"))
        self.stdout.write(self.style.SUCCESS(f"✓ Organization created: '{org.name}' [Active, Approved, Enterprise Tier]"))
        self.stdout.write(self.style.SUCCESS(f"✓ HR / Recruiters (2): '{hr1.username}', '{hr2.username}'"))
        self.stdout.write(self.style.SUCCESS(f"✓ Candidates (3): '{cand1.username}', '{cand2.username}', '{cand3.username}'"))
        self.stdout.write(self.style.SUCCESS(f"✓ Freelancers (2): '{free1.username}', '{free2.username}'"))
        self.stdout.write(self.style.SUCCESS(f"✓ Active Job Postings: {len(created_jobs)} jobs seeded (Find Jobs counter = {len(created_jobs)})"))
        self.stdout.write(self.style.SUCCESS("✓ Applications & Freelance Gigs seeded"))
        self.stdout.write(self.style.SUCCESS("✓ Rate limits and login lockout counters cleared"))

        if generated_password:
            self.stdout.write(self.style.WARNING("\n" + "=" * 65))
            self.stdout.write(self.style.WARNING(f"Generated Demo User Password: {raw_password}"))
            self.stdout.write(self.style.WARNING("All seeded accounts (Company Admin, HR, Candidates, Freelancers)"))
            self.stdout.write(self.style.WARNING("share this password for testing."))
            self.stdout.write(self.style.WARNING("=" * 65 + "\n"))
        else:
            self.stdout.write(self.style.SUCCESS("✓ Test user password configured from TEST_USER_PASSWORD in .env"))
